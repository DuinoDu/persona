#!/usr/bin/env python3
import argparse
import os
import json
import time
from pathlib import Path

import torch
from peft import LoraConfig, TaskType, get_peft_model
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed


def _identity_compile(fn=None, *args, **kwargs):
    if fn is None:
        def _decorator(f):
            return f
        return _decorator
    return fn


torch.compile = _identity_compile


class ChatJsonlDataset(Dataset):
    def __init__(self, path: Path, tokenizer, cutoff_len: int, max_samples: int):
        self.samples = []
        with path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if max_samples and idx >= max_samples:
                    break
                row = json.loads(line)
                tokenized = tokenizer.apply_chat_template(
                    row["messages"],
                    tokenize=True,
                    add_generation_prompt=False,
                )
                if hasattr(tokenized, "ids"):
                    token_ids = tokenized.ids
                elif isinstance(tokenized, dict) and "input_ids" in tokenized:
                    token_ids = tokenized["input_ids"]
                elif hasattr(tokenized, "input_ids"):
                    token_ids = tokenized.input_ids
                else:
                    token_ids = tokenized
                if token_ids:
                    self.samples.append(list(token_ids)[:cutoff_len])

        if not self.samples:
            raise RuntimeError(f"no valid samples loaded from {path}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def build_collator(pad_token_id: int):
    def collate(batch):
        max_len = max(len(x) for x in batch)
        input_ids = torch.full((len(batch), max_len), pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((len(batch), max_len), dtype=torch.long)
        labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
        for i, ids in enumerate(batch):
            ids_t = torch.tensor(ids, dtype=torch.long)
            seq_len = ids_t.shape[0]
            input_ids[i, :seq_len] = ids_t
            attention_mask[i, :seq_len] = 1
            labels[i, :seq_len] = ids_t
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


def cycle(loader):
    while True:
        for batch in loader:
            yield batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-samples", type=int, default=32)
    parser.add_argument("--cutoff-len", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    set_seed(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA is required for this smoke run")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    dataset = ChatJsonlDataset(Path(args.train_file), tokenizer, args.cutoff_len, args.max_samples)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
        collate_fn=build_collator(tokenizer.pad_token_id),
    )

    print(f"loaded_samples={len(dataset)}", flush=True)
    print(f"device={device}", flush=True)
    print(f"torch_num_threads={torch.get_num_threads()}", flush=True)
    print(f"torch_num_interop_threads={torch.get_num_interop_threads()}", flush=True)
    print("stage=load_model_start", flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        device_map={"": 0},
    )
    print("stage=load_model_done", flush=True)
    print(f"first_param_device={next(model.parameters()).device}", flush=True)

    print("stage=lora_inject_start", flush=True)
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "v_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    print("stage=lora_inject_done", flush=True)
    model.train()
    print("stage=model_train_mode_done", flush=True)

    trainable, total = count_trainable_params(model)
    print(f"trainable_params={trainable}", flush=True)
    print(f"total_params={total}", flush=True)

    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=args.learning_rate)
    print("stage=optimizer_init_done", flush=True)

    step_losses = []
    data_iter = cycle(loader)
    start_time = time.time()
    torch.cuda.reset_peak_memory_stats(device)

    for step in range(1, args.max_steps + 1):
        batch = next(data_iter)
        batch = {k: v.to(device, non_blocking=False) for k, v in batch.items()}
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            outputs = model(**batch)
            loss = outputs.loss
        loss.backward()
        optimizer.step()
        loss_value = float(loss.detach().cpu().item())
        step_losses.append(loss_value)
        current_mem = torch.cuda.memory_allocated(device) / 1024 / 1024 / 1024
        peak_mem = torch.cuda.max_memory_allocated(device) / 1024 / 1024 / 1024
        print(
            f"step={step}/{args.max_steps} loss={loss_value:.6f} gpu_mem_gb={current_mem:.2f} peak_gpu_mem_gb={peak_mem:.2f}",
            flush=True,
        )

    elapsed = time.time() - start_time
    adapter_dir = out_dir / "manual_smoke_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    metrics = {
        "model_path": args.model_path,
        "train_file": args.train_file,
        "max_steps": args.max_steps,
        "max_samples": len(dataset),
        "cutoff_len": args.cutoff_len,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "loss_first": step_losses[0],
        "loss_last": step_losses[-1],
        "elapsed_sec": elapsed,
        "peak_gpu_mem_gb": torch.cuda.max_memory_allocated(device) / 1024 / 1024 / 1024,
    }
    (out_dir / "manual_smoke_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
