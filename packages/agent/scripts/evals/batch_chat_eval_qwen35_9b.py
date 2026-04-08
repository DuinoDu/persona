#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def _identity_compile(fn=None, *args, **kwargs):
    if fn is None:
        def _decorator(f):
            return f
        return _decorator
    return fn


torch.compile = _identity_compile

CONTROL_TOKEN_RE = re.compile(r"<\|[^>]+\|>")
ARTIFACT_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize_artifact_name(value: str):
    normalized = ARTIFACT_NAME_RE.sub("_", value)
    return normalized.strip("._-") or "item"


def resolve_model_dtype(device: str):
    raw = (os.getenv("PERSONA_INFER_DTYPE", "") or ("float16" if device == "cuda" else "float32")).strip().lower()
    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "half": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    if raw not in mapping:
        raise ValueError(f"unsupported PERSONA_INFER_DTYPE={raw}")
    return raw, mapping[raw]


def configure_runtime(attn_implementation: str):
    torch.backends.cuda.matmul.allow_tf32 = True
    try:
        torch.set_num_threads(1)
    except RuntimeError:
        pass
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    if torch.cuda.is_available() and attn_implementation == "eager":
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        torch.backends.cuda.enable_math_sdp(True)


def load_jsonl_cases(path: Path, *, default_slice: str | None = None, start_index: int = 1):
    items = []
    next_index = start_index
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            payload.setdefault("id", payload.get("benchmark_id") or f"case-{next_index:04d}")
            if default_slice and not payload.get("slice"):
                payload["slice"] = default_slice
            items.append(payload)
            next_index += 1
    return items, next_index


def load_suite(path: Path):
    if path.is_dir():
        suite_meta_path = path / "suite.json"
        cases_dir = path / "cases"
        suite_meta = {}
        if suite_meta_path.exists():
            suite_meta = json.loads(suite_meta_path.read_text(encoding="utf-8"))
        if not cases_dir.exists() or not cases_dir.is_dir():
            raise ValueError(f"suite dir {path} missing cases/")

        items = []
        next_index = 1
        for case_file in sorted(cases_dir.glob("*.jsonl")):
            file_items, next_index = load_jsonl_cases(
                case_file,
                default_slice=case_file.stem,
                start_index=next_index,
            )
            items.extend(file_items)
        return items, suite_meta

    items, _ = load_jsonl_cases(path)
    return items, None


def normalize_messages(item: dict, default_system_prompt: str):
    messages = item.get("messages")
    if not isinstance(messages, list) or not messages:
        user_text = str(item.get("user_text") or item.get("prompt") or "").strip()
        if not user_text:
            raise ValueError(f"case {item.get('id')} missing messages/user_text")
        messages = [{"role": "user", "content": user_text}]

    normalized = []
    has_system = False
    for message in messages:
        role = str(message.get("role") or "").strip()
        if role == "persona":
            role = "assistant"
        content = str(message.get("content") or message.get("text") or "")
        if not role:
            raise ValueError(f"case {item.get('id')} has message without role")
        if role == "system":
            has_system = True
        normalized.append({"role": role, "content": content})

    inline_system = str(item.get("system_prompt") or "").strip()
    system_prompt = inline_system or default_system_prompt
    if system_prompt and not has_system:
        normalized = [{"role": "system", "content": system_prompt}] + normalized
    return normalized


def resolve_prompt_version(system_prompt_file: str):
    if not system_prompt_file:
        return "default"
    return Path(system_prompt_file).stem or Path(system_prompt_file).name or "default"


def build_runtime_signature(
    *,
    deployment_id: str,
    deployment_slug: str,
    base_model_path: str,
    adapter_path: str,
    system_prompt_file: str,
    device: str,
    runner_kind: str,
    service_mode: str,
    prompt_version: str,
    generation_config_version: str,
    context_builder_version: str,
):
    return {
        "deployment_id": deployment_id or deployment_slug or "unknown",
        "deployment_slug": deployment_slug or None,
        "base_model_path": base_model_path,
        "adapter_path": adapter_path or None,
        "system_prompt_file": system_prompt_file or None,
        "device": device,
        "runner_kind": runner_kind,
        "service_mode": service_mode,
        "prompt_version": prompt_version or resolve_prompt_version(system_prompt_file),
        "generation_config_version": generation_config_version or "v1",
        "context_builder_version": context_builder_version or "v1",
    }


def build_generation_config(max_new_tokens: int, do_sample: bool, temperature: float, top_p: float):
    return {
        "max_new_tokens": int(max_new_tokens),
        "do_sample": bool(do_sample),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }


def build_inference_request(messages, generation_config, trace_meta, runtime_signature):
    return {
        "runtime_signature": runtime_signature,
        "messages": messages,
        "generation": generation_config,
        "trace_meta": trace_meta,
    }


def clean_output(text: str):
    cleaned = CONTROL_TOKEN_RE.sub("", text)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def maybe_disable_qwen_fast_path():
    disable_fla = os.getenv("PERSONA_DISABLE_FLA", "0") == "1"
    disable_causal_conv1d = os.getenv("PERSONA_DISABLE_CAUSAL_CONV1D", "0") == "1"
    if not (disable_fla or disable_causal_conv1d):
        return disable_fla, disable_causal_conv1d
    import sys
    from transformers.utils import import_utils as hf_import_utils

    if disable_fla:
        hf_import_utils.is_flash_linear_attention_available = lambda: False
    if disable_causal_conv1d:
        hf_import_utils.is_causal_conv1d_available = lambda: False
    for mod_name in list(sys.modules):
        if mod_name.startswith("transformers.models.qwen3_5"):
            del sys.modules[mod_name]
    return disable_fla, disable_causal_conv1d


def build_model(base_model_path: str, adapter_path: str, device: str):
    attn_implementation = os.getenv("PERSONA_ATTN_IMPLEMENTATION", "") or "eager"
    infer_dtype_name, infer_dtype = resolve_model_dtype(device)
    configure_runtime(attn_implementation)
    disable_fla, disable_causal_conv1d = maybe_disable_qwen_fast_path()
    print(f"fastpath_disable_fla={disable_fla}", flush=True)
    print(f"fastpath_disable_causal_conv1d={disable_causal_conv1d}", flush=True)
    print(f"attn_implementation={attn_implementation}", flush=True)
    print(f"infer_dtype={infer_dtype_name}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    load_kwargs = dict(
        trust_remote_code=True,
        dtype=infer_dtype,
        low_cpu_mem_usage=True,
        attn_implementation=attn_implementation,
    )
    if device == "cuda":
        load_kwargs["device_map"] = {"": 0}
    print("stage=load_model_start", flush=True)
    model = AutoModelForCausalLM.from_pretrained(base_model_path, **load_kwargs)
    print("stage=load_model_done", flush=True)
    if adapter_path:
        print(f"stage=load_adapter_start adapter={adapter_path}", flush=True)
        model = PeftModel.from_pretrained(model, adapter_path)
        print("stage=load_adapter_done", flush=True)
    if device == "cpu":
        model.to("cpu")
    model.eval()
    if hasattr(model, "config"):
        model.config.use_cache = True
    return tokenizer, model


def pick_next_token(next_token_logits: torch.Tensor, do_sample: bool, temperature: float, top_p: float) -> torch.Tensor:
    if next_token_logits.shape[0] != 1:
        raise RuntimeError("only batch_size=1 is supported")
    if not do_sample:
        return torch.argmax(next_token_logits, dim=-1, keepdim=True)

    logits = next_token_logits[0]
    if temperature and temperature > 0:
        logits = logits / temperature
    if top_p is not None and 0 < top_p < 1.0:
        sorted_logits, sorted_indices = torch.sort(logits, descending=True)
        sorted_probs = torch.softmax(sorted_logits, dim=-1)
        cumulative_probs = torch.cumsum(sorted_probs, dim=-1)
        keep_mask = cumulative_probs <= top_p
        if keep_mask.numel() > 0:
            keep_mask[0] = True
        filtered_logits = torch.full_like(logits, float("-inf"))
        filtered_logits.scatter_(0, sorted_indices[keep_mask], logits[sorted_indices[keep_mask]])
        probs = torch.softmax(filtered_logits, dim=-1)
    else:
        probs = torch.softmax(logits, dim=-1)
    next_token = torch.multinomial(probs, num_samples=1)
    return next_token.view(1, 1)


def generate_tokens(model, inputs: dict, max_new_tokens: int, eos_token_id, do_sample: bool, temperature: float, top_p: float):
    input_ids = inputs["input_ids"]
    attention_mask = inputs.get("attention_mask")
    if attention_mask is None:
        attention_mask = torch.ones_like(input_ids)

    eos_token_ids = []
    if eos_token_id is None:
        eos_token_ids = []
    elif isinstance(eos_token_id, int):
        eos_token_ids = [eos_token_id]
    else:
        eos_token_ids = list(eos_token_id)

    generated = []
    started = time.time()
    autocast_dtype = next(model.parameters()).dtype
    use_autocast = input_ids.device.type == "cuda" and autocast_dtype in {torch.float16, torch.bfloat16}
    step_input_ids = input_ids
    past_key_values = None

    for _ in range(max_new_tokens):
        with torch.no_grad():
            model_kwargs = dict(
                input_ids=step_input_ids,
                attention_mask=attention_mask,
                use_cache=True,
                logits_to_keep=0,
                return_dict=True,
            )
            if past_key_values is not None:
                model_kwargs["past_key_values"] = past_key_values
            if use_autocast:
                with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                    outputs = model(**model_kwargs)
            else:
                outputs = model(**model_kwargs)
        past_key_values = outputs.past_key_values
        next_token_logits = outputs.logits[:, -1, :]
        next_token = pick_next_token(next_token_logits, do_sample=do_sample, temperature=temperature, top_p=top_p)
        generated.append(next_token)
        step_input_ids = next_token
        attention_mask = torch.cat(
            [
                attention_mask,
                torch.ones((attention_mask.shape[0], 1), dtype=attention_mask.dtype, device=attention_mask.device),
            ],
            dim=-1,
        )
        if eos_token_ids and int(next_token.item()) in eos_token_ids:
            break

    latency_ms = int((time.time() - started) * 1000)
    if generated:
        new_tokens = torch.cat(generated, dim=-1)
    else:
        new_tokens = input_ids[:, 0:0]
    return new_tokens, latency_ms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model-path", required=True)
    parser.add_argument("--adapter-path", default="")
    parser.add_argument("--suite-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--system-prompt-file", default="")
    parser.add_argument("--deployment-id", default="")
    parser.add_argument("--deployment-slug", default="")
    parser.add_argument("--prompt-version", default="")
    parser.add_argument("--generation-config-version", default="v1")
    parser.add_argument("--context-builder-version", default="v1")
    parser.add_argument("--trace-dir", default="")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--do-sample", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.95)
    args = parser.parse_args()

    suite_path = Path(args.suite_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = Path(args.trace_dir) if args.trace_dir else output_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    default_system_prompt = ""
    if args.system_prompt_file:
        default_system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")

    suite, suite_meta = load_suite(suite_path)
    print(f"suite_cases={len(suite)} path={suite_path}", flush=True)
    print(f"stage=load_model base={args.base_model_path} adapter={args.adapter_path or '-'} device={args.device}", flush=True)
    tokenizer, model = build_model(args.base_model_path, args.adapter_path, args.device)
    target_device = next(model.parameters()).device
    runtime_signature = build_runtime_signature(
        deployment_id=args.deployment_id,
        deployment_slug=args.deployment_slug,
        base_model_path=args.base_model_path,
        adapter_path=args.adapter_path,
        system_prompt_file=args.system_prompt_file,
        device=args.device,
        runner_kind="batch_chat_eval",
        service_mode="offline_eval",
        prompt_version=args.prompt_version,
        generation_config_version=args.generation_config_version,
        context_builder_version=args.context_builder_version,
    )
    generation_config = build_generation_config(
        args.max_new_tokens,
        args.do_sample,
        args.temperature,
        args.top_p,
    )

    generations_path = output_dir / "generations.jsonl"
    summary_path = output_dir / "summary.json"
    manifest_path = output_dir / "run_manifest.json"

    generated_records = []
    blank_count = 0
    short_count = 0
    control_token_count = 0
    total_prompt_tokens = 0
    total_generated_tokens = 0
    slice_stats = {}

    started_at = time.time()
    with generations_path.open("w", encoding="utf-8") as out:
        for index, item in enumerate(suite, start=1):
            case_id = str(item.get("id") or f"case-{index:04d}")
            messages = normalize_messages(item, default_system_prompt)
            inputs = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            inputs = {k: v.to(target_device) for k, v in inputs.items()}
            prompt_tokens = int(inputs["input_ids"].shape[-1])
            total_prompt_tokens += prompt_tokens

            new_tokens, latency_ms = generate_tokens(
                model,
                inputs,
                max_new_tokens=args.max_new_tokens,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=args.do_sample,
                temperature=args.temperature,
                top_p=args.top_p,
            )
            raw_text = tokenizer.decode(new_tokens[0], skip_special_tokens=False)
            clean_text = clean_output(raw_text)
            generated_tokens = int(new_tokens.shape[-1])
            total_generated_tokens += generated_tokens
            contains_control_tokens = bool(CONTROL_TOKEN_RE.search(raw_text))
            blank_output = not clean_text.strip()
            short_output = len(clean_text) < 30
            if blank_output:
                blank_count += 1
            if short_output:
                short_count += 1
            if contains_control_tokens:
                control_token_count += 1

            slice_name = str(item.get("slice") or "unspecified")
            stats = slice_stats.setdefault(slice_name, {"count": 0, "blank": 0, "short": 0})
            stats["count"] += 1
            stats["blank"] += int(blank_output)
            stats["short"] += int(short_output)
            trace_meta = {
                "case_index": index,
                "case_id": case_id,
                "request_id": case_id,
                "slice": slice_name,
                "tags": item.get("tags") or [],
                "suite_path": str(suite_path),
            }
            trace_path = trace_dir / f"{sanitize_artifact_name(case_id)}.json"
            trace_record = {
                "kind": "persona_batch_case_trace_v1",
                "request_id": case_id,
                "case_id": case_id,
                "slice": slice_name,
                "tags": item.get("tags") or [],
                "runtime_signature": runtime_signature,
                "request": build_inference_request(messages, generation_config, trace_meta, runtime_signature),
                "response": {
                    "raw_output_text": raw_text,
                    "clean_output_text": clean_text,
                    "generated_tokens": generated_tokens,
                    "prompt_tokens": prompt_tokens,
                    "latency_ms": latency_ms,
                    "contains_control_tokens": contains_control_tokens,
                    "blank_output": blank_output,
                    "short_output": short_output,
                },
                "metrics": {
                    "prompt_tokens": prompt_tokens,
                    "generated_tokens": generated_tokens,
                    "latency_ms": latency_ms,
                    "output_char_len": len(clean_text),
                },
                "artifacts": {
                    "trace_path": str(trace_path),
                    "trace_dir": str(trace_dir),
                    "generations_path": str(generations_path),
                },
            }
            trace_path.write_text(json.dumps(trace_record, ensure_ascii=False, indent=2), encoding="utf-8")

            record = {
                "id": case_id,
                "slice": slice_name,
                "tags": item.get("tags") or [],
                "messages": messages,
                "runtime_signature": runtime_signature,
                "generation": generation_config,
                "prompt_tokens": prompt_tokens,
                "generated_tokens": generated_tokens,
                "latency_ms": latency_ms,
                "raw_output_text": raw_text,
                "clean_output_text": clean_text,
                "output_char_len": len(clean_text),
                "blank_output": blank_output,
                "short_output": short_output,
                "contains_control_tokens": contains_control_tokens,
                "trace_path": str(trace_path),
            }
            generated_records.append(record)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"case={index}/{len(suite)} id={case_id} slice={slice_name} prompt_tokens={prompt_tokens} generated_tokens={generated_tokens} latency_ms={latency_ms}",
                flush=True,
            )

    elapsed_sec = time.time() - started_at
    summary = {
        "suite_path": str(suite_path),
        "suite_meta": suite_meta,
        "output_dir": str(output_dir),
        "trace_dir": str(trace_dir),
        "base_model_path": args.base_model_path,
        "adapter_path": args.adapter_path,
        "system_prompt_file": args.system_prompt_file,
        "device": args.device,
        "runtime_signature": runtime_signature,
        "generation_config": generation_config,
        "do_sample": args.do_sample,
        "temperature": args.temperature if args.do_sample else None,
        "top_p": args.top_p if args.do_sample else None,
        "max_new_tokens": args.max_new_tokens,
        "case_count": len(generated_records),
        "blank_count": blank_count,
        "short_count": short_count,
        "control_token_count": control_token_count,
        "avg_prompt_tokens": (total_prompt_tokens / len(generated_records)) if generated_records else 0,
        "avg_generated_tokens": (total_generated_tokens / len(generated_records)) if generated_records else 0,
        "avg_output_chars": (sum(item["output_char_len"] for item in generated_records) / len(generated_records)) if generated_records else 0,
        "elapsed_sec": elapsed_sec,
        "slice_stats": slice_stats,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "suite_path": str(suite_path),
        "suite_meta": suite_meta,
        "generations_path": str(generations_path),
        "summary_path": str(summary_path),
        "trace_dir": str(trace_dir),
        "runtime_signature": runtime_signature,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved_generations={generations_path}", flush=True)
    print(f"saved_summary={summary_path}", flush=True)


if __name__ == "__main__":
    main()
