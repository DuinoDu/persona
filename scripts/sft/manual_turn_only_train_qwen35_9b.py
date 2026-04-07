#!/usr/bin/env python3
import argparse
import json
import math
import os
import time
import sys
from pathlib import Path

import torch
from peft import LoraConfig, TaskType, get_peft_model
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup, set_seed


def _identity_compile(fn=None, *args, **kwargs):
    if fn is None:
        def _decorator(f):
            return f
        return _decorator
    return fn


torch.compile = _identity_compile

DEFAULT_TARGET_MODULES = (
    "in_proj_a,in_proj_b,in_proj_qkv,in_proj_z,out_proj,"
    "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj"
)
IM_START = "<|im_start|>"
IM_END = "<|im_end|>"


class LazyChatJsonlDataset(Dataset):
    def __init__(self, path: Path, tokenizer, cutoff_len: int, max_samples: int = 0):
        self.path = Path(path)
        self.tokenizer = tokenizer
        self.cutoff_len = cutoff_len
        self.offsets = []
        self._fh = None
        with self.path.open("rb") as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                if line.strip():
                    self.offsets.append(offset)
        if max_samples and max_samples > 0:
            self.offsets = self.offsets[:max_samples]
        if not self.offsets:
            raise RuntimeError(f"no valid samples found in {self.path}")

    def __len__(self):
        return len(self.offsets)

    def __del__(self):
        if self._fh is not None and not self._fh.closed:
            self._fh.close()

    def _get_fh(self):
        if self._fh is None or self._fh.closed:
            self._fh = self.path.open("r", encoding="utf-8")
        return self._fh

    def _build_supervised_example(self, messages, sample_id: str):
        rendered = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        tokenized = self.tokenizer(
            rendered,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        token_ids = list(tokenized["input_ids"])
        offset_mapping = tokenized["offset_mapping"]
        labels = [-100] * len(token_ids)

        cursor = 0
        assistant_spans = []
        for msg_idx, message in enumerate(messages):
            role = message["role"]
            marker = f"{IM_START}{role}\n"
            marker_pos = rendered.find(marker, cursor)
            if marker_pos < 0:
                raise RuntimeError(
                    f"failed to locate marker for sample={sample_id} msg_idx={msg_idx} role={role}"
                )
            block_start = marker_pos + len(marker)
            end_marker_pos = rendered.find(IM_END, block_start)
            if end_marker_pos < 0:
                raise RuntimeError(
                    f"failed to locate end marker for sample={sample_id} msg_idx={msg_idx} role={role}"
                )
            if role == "assistant":
                assistant_spans.append((block_start, end_marker_pos + len(IM_END)))
            cursor = end_marker_pos + len(IM_END)

        if not assistant_spans:
            raise RuntimeError(f"no assistant spans found for sample={sample_id}")

        for idx, ((char_start, char_end), token_id) in enumerate(zip(offset_mapping, token_ids)):
            if char_end <= char_start:
                continue
            for span_start, span_end in assistant_spans:
                if char_start < span_end and char_end > span_start:
                    labels[idx] = token_id
                    break

        if len(token_ids) > self.cutoff_len:
            token_ids = token_ids[-self.cutoff_len:]
            labels = labels[-self.cutoff_len:]

        if not token_ids:
            raise RuntimeError(f"empty sample at sample_id={sample_id} path={self.path}")
        if all(label == -100 for label in labels):
            raise RuntimeError(f"no supervised tokens after truncation for sample={sample_id} path={self.path}")
        return {
            "input_ids": token_ids,
            "labels": labels,
        }

    def __getitem__(self, idx):
        fh = self._get_fh()
        fh.seek(self.offsets[idx])
        row = json.loads(fh.readline())
        sample_id = row.get("turn_sample_id") or row.get("conversation_id") or str(idx)
        return self._build_supervised_example(row["messages"], sample_id=sample_id)


def build_collator(pad_token_id: int):
    def collate(batch):
        max_len = max(len(x["input_ids"]) for x in batch)
        input_ids = torch.full((len(batch), max_len), pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
        labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
        for i, sample in enumerate(batch):
            ids_t = torch.tensor(sample["input_ids"], dtype=torch.long)
            labels_t = torch.tensor(sample["labels"], dtype=torch.long)
            seq_len = ids_t.shape[0]
            input_ids[i, :seq_len] = ids_t
            attention_mask[i, :seq_len] = 1
            labels[i, :seq_len] = labels_t
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

    return collate


def count_trainable_params(model):
    total = 0
    trainable = 0
    for p in model.parameters():
        n = p.numel()
        total += n
        if p.requires_grad:
            trainable += n
    return trainable, total


def save_adapter(model, tokenizer, out_dir: Path, tag: str, meta: dict):
    ckpt_dir = out_dir / tag
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ckpt_dir)
    tokenizer.save_pretrained(ckpt_dir)
    (ckpt_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return ckpt_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--num-epochs", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--cutoff-len", type=int, default=4096)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--save-steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lora-r", type=int, default=64)
    parser.add_argument("--lora-alpha", type=int, default=128)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--target-modules", default=DEFAULT_TARGET_MODULES)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--gradient-checkpointing", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_jsonl_path = out_dir / "train_log.jsonl"

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    set_seed(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required")

    disable_fla = os.getenv("PERSONA_DISABLE_FLA", "0") == "1"
    disable_causal_conv1d = os.getenv("PERSONA_DISABLE_CAUSAL_CONV1D", "0") == "1"
    attn_implementation = os.getenv("PERSONA_ATTN_IMPLEMENTATION", "")
    gc_use_reentrant_env = os.getenv("PERSONA_GC_USE_REENTRANT", "")
    gc_use_reentrant = None if gc_use_reentrant_env == "" else gc_use_reentrant_env == "1"
    if disable_fla or disable_causal_conv1d:
        from transformers.utils import import_utils as hf_import_utils
        if disable_fla:
            hf_import_utils.is_flash_linear_attention_available = lambda: False
        if disable_causal_conv1d:
            hf_import_utils.is_causal_conv1d_available = lambda: False
        for mod_name in list(sys.modules):
            if mod_name.startswith("transformers.models.qwen3_5"):
                del sys.modules[mod_name]
    if attn_implementation == "eager":
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)
    print(f"fastpath_disable_fla={disable_fla}", flush=True)
    print(f"fastpath_disable_causal_conv1d={disable_causal_conv1d}", flush=True)
    print(f"attn_implementation={attn_implementation or 'default'}", flush=True)
    print(f"gc_use_reentrant={gc_use_reentrant if gc_use_reentrant is not None else 'default'}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"device={device}", flush=True)
    print("stage=load_model_start", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        device_map={"": 0},
        attn_implementation=attn_implementation or None,
    )
    print("stage=load_model_done", flush=True)

    if args.gradient_checkpointing:
        gc_kwargs = None if gc_use_reentrant is None else {"use_reentrant": gc_use_reentrant}
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs=gc_kwargs)
        model.config.use_cache = False
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        print(f"stage=gradient_checkpointing_enabled gc_use_reentrant={gc_use_reentrant if gc_use_reentrant is not None else 'default'}", flush=True)

    print("stage=lora_inject_start", flush=True)
    target_modules = [m.strip() for m in args.target_modules.split(",") if m.strip()]
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=target_modules,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.train()
    print("stage=lora_inject_done", flush=True)

    trainable, total = count_trainable_params(model)
    print(f"trainable_params={trainable}", flush=True)
    print(f"total_params={total}", flush=True)

    trainable_params_for_optim = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable_params_for_optim,
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    print("stage=optimizer_ready", flush=True)

    dataset = LazyChatJsonlDataset(
        Path(args.train_file),
        tokenizer=tokenizer,
        cutoff_len=args.cutoff_len,
        max_samples=args.max_samples,
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=False,
        collate_fn=build_collator(tokenizer.pad_token_id),
    )

    updates_per_epoch = math.ceil(len(loader) / args.gradient_accumulation_steps)
    total_steps = args.max_steps if args.max_steps > 0 else updates_per_epoch * args.num_epochs
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=max(1, total_steps),
    )
    print(f"loaded_samples={len(dataset)}", flush=True)
    print(f"updates_per_epoch={updates_per_epoch}", flush=True)
    print(f"total_steps={total_steps}", flush=True)
    print("stage=optimizer_scheduler_ready", flush=True)

    run_config = {
        "model_path": args.model_path,
        "train_file": args.train_file,
        "output_dir": str(out_dir),
        "dataset_size": len(dataset),
        "num_epochs": args.num_epochs,
        "max_steps": args.max_steps,
        "total_steps": total_steps,
        "updates_per_epoch": updates_per_epoch,
        "cutoff_len": args.cutoff_len,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "effective_batch_size": args.batch_size * args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "warmup_ratio": args.warmup_ratio,
        "warmup_steps": warmup_steps,
        "max_grad_norm": args.max_grad_norm,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "target_modules": target_modules,
        "gradient_checkpointing": args.gradient_checkpointing,
        "gc_use_reentrant": gc_use_reentrant,
        "seed": args.seed,
        "loss_mask": "assistant_tokens_only",
        "truncation": "keep_last_cutoff_tokens",
    }
    (out_dir / "run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    global_step = 0
    accum_loss = 0.0
    accum_count = 0
    start_time = time.time()
    torch.cuda.reset_peak_memory_stats(device)
    optimizer.zero_grad(set_to_none=True)

    with log_jsonl_path.open("a", encoding="utf-8") as log_f:
        stop_training = False
        for epoch in range(1, args.num_epochs + 1):
            for batch_idx, batch in enumerate(loader, start=1):
                batch = {k: v.to(device, non_blocking=False) for k, v in batch.items()}
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    outputs = model(**batch)
                    loss = outputs.loss
                loss_value = float(loss.detach().cpu().item())
                (loss / args.gradient_accumulation_steps).backward()
                accum_loss += loss_value
                accum_count += 1

                is_update_step = accum_count == args.gradient_accumulation_steps or batch_idx == len(loader)
                if not is_update_step:
                    continue

                grad_norm = None
                if args.max_grad_norm and args.max_grad_norm > 0:
                    grad_norm = float(torch.nn.utils.clip_grad_norm_(trainable_params_for_optim, args.max_grad_norm).detach().cpu().item())
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1

                avg_loss = accum_loss / accum_count
                accum_loss = 0.0
                accum_count = 0

                current_mem = torch.cuda.memory_allocated(device) / 1024 / 1024 / 1024
                peak_mem = torch.cuda.max_memory_allocated(device) / 1024 / 1024 / 1024
                lr = scheduler.get_last_lr()[0]
                elapsed = time.time() - start_time
                step_record = {
                    "step": global_step,
                    "epoch": epoch,
                    "loss": avg_loss,
                    "learning_rate": lr,
                    "grad_norm": grad_norm,
                    "gpu_mem_gb": current_mem,
                    "peak_gpu_mem_gb": peak_mem,
                    "elapsed_sec": elapsed,
                }
                log_f.write(json.dumps(step_record) + "\n")
                log_f.flush()

                if global_step == 1 or global_step % args.logging_steps == 0:
                    grad_norm_str = f"{grad_norm:.6f}" if grad_norm is not None else "nan"
                    print(
                        f"step={global_step}/{total_steps} epoch={epoch}/{args.num_epochs} "
                        f"loss={avg_loss:.6f} lr={lr:.6e} grad_norm={grad_norm_str} "
                        f"gpu_mem_gb={current_mem:.2f} peak_gpu_mem_gb={peak_mem:.2f}",
                        flush=True,
                    )

                if args.save_steps > 0 and global_step % args.save_steps == 0:
                    meta = {
                        "global_step": global_step,
                        "epoch": epoch,
                        "elapsed_sec": elapsed,
                        "loss": avg_loss,
                        "learning_rate": lr,
                        "peak_gpu_mem_gb": peak_mem,
                    }
                    ckpt_dir = save_adapter(model, tokenizer, out_dir, f"checkpoint-{global_step}", meta)
                    print(f"saved_checkpoint={ckpt_dir}", flush=True)

                if global_step >= total_steps:
                    stop_training = True
                    break
            if stop_training:
                break

    final_meta = {
        "global_step": global_step,
        "elapsed_sec": time.time() - start_time,
        "peak_gpu_mem_gb": torch.cuda.max_memory_allocated(device) / 1024 / 1024 / 1024,
        "dataset_size": len(dataset),
        "total_steps": total_steps,
    }
    final_dir = save_adapter(model, tokenizer, out_dir, "final_adapter", final_meta)
    (out_dir / "train_summary.json").write_text(json.dumps(final_meta, indent=2), encoding="utf-8")
    print(json.dumps(final_meta, indent=2), flush=True)
    print(f"final_adapter_dir={final_dir}", flush=True)


if __name__ == "__main__":
    main()
