#!/usr/bin/env python3
import argparse
import json
import os
import re
import socketserver
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

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
SERVICE_STATE = {
    "ready": False,
    "loading": True,
    "error": None,
    "deployment_id": None,
    "deployment_slug": None,
    "base_model_path": None,
    "adapter_path": None,
    "system_prompt_file": None,
    "device": None,
    "prompt_version": None,
    "generation_config_version": None,
    "context_builder_version": None,
    "default_max_new_tokens": None,
    "trace_dir": None,
    "started_at": time.time(),
}
MODEL_BUNDLE = {
    "tokenizer": None,
    "model": None,
    "generate_lock": threading.Lock(),
    "default_system_prompt": "",
}
REQUEST_STATE = {
    "counter": 0,
    "lock": threading.Lock(),
}


def clean_output(text: str) -> str:
    cleaned = CONTROL_TOKEN_RE.sub("", text)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


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


def maybe_disable_qwen_fast_path() -> tuple[bool, bool]:
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


def resolve_prompt_version(system_prompt_file: str):
    if not system_prompt_file:
        return "default"
    path = Path(system_prompt_file)
    return path.stem or path.name or "default"


def next_request_id():
    with REQUEST_STATE["lock"]:
        REQUEST_STATE["counter"] += 1
        seq = REQUEST_STATE["counter"]
    return f"req_{int(time.time() * 1000)}_{seq:04d}"


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


def default_trace_dir():
    trace_dir = SERVICE_STATE.get("trace_dir")
    if trace_dir:
        return Path(trace_dir)
    token_source = SERVICE_STATE.get("deployment_slug") or SERVICE_STATE.get("base_model_path") or "live"
    token = sanitize_artifact_name(Path(str(token_source)).name or str(token_source))
    return Path.cwd() / "runtime_logs" / "live" / token / "traces"


def build_trace_path(request_id: str):
    trace_dir = default_trace_dir()
    trace_dir.mkdir(parents=True, exist_ok=True)
    return trace_dir / f"{sanitize_artifact_name(request_id)}.json"


def write_trace_artifact(trace_path: Path, trace_record: dict):
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace_record, ensure_ascii=False, indent=2), encoding="utf-8")


def build_model(base_model_path: str, adapter_path: str, system_prompt_file: str, device: str):
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
    default_system_prompt = ""
    if system_prompt_file:
        default_system_prompt = Path(system_prompt_file).read_text(encoding="utf-8")
    return tokenizer, model, default_system_prompt


def normalize_messages(payload_messages, default_system_prompt: str):
    if not isinstance(payload_messages, list) or not payload_messages:
        raise ValueError("messages must be a non-empty list")

    messages = []
    has_system = False
    for message in payload_messages:
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"unsupported role: {role}")
        if role == "system":
            has_system = True
        messages.append({"role": role, "content": content})

    if default_system_prompt and not has_system:
        messages = [{"role": "system", "content": default_system_prompt}] + messages
    return messages


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


def prepare_generation(payload: dict, route_name: str) -> dict:
    if not SERVICE_STATE["ready"]:
        raise RuntimeError(SERVICE_STATE["error"] or "service not ready")

    tokenizer = MODEL_BUNDLE["tokenizer"]
    model = MODEL_BUNDLE["model"]
    default_system_prompt = MODEL_BUNDLE["default_system_prompt"]
    messages = normalize_messages(payload.get("messages"), default_system_prompt)
    max_new_tokens = int(payload.get("max_new_tokens") or SERVICE_STATE["default_max_new_tokens"] or 256)
    do_sample = bool(payload.get("do_sample", False))
    temperature = float(payload.get("temperature") or 0.7)
    top_p = float(payload.get("top_p") or 0.95)
    request_id = str(payload.get("request_id") or next_request_id())
    incoming_trace_meta = payload.get("trace_meta") if isinstance(payload.get("trace_meta"), dict) else {}
    runtime_signature = build_runtime_signature(
        deployment_id=str(SERVICE_STATE.get("deployment_id") or ""),
        deployment_slug=str(SERVICE_STATE.get("deployment_slug") or ""),
        base_model_path=str(SERVICE_STATE.get("base_model_path") or ""),
        adapter_path=str(SERVICE_STATE.get("adapter_path") or ""),
        system_prompt_file=str(SERVICE_STATE.get("system_prompt_file") or ""),
        device=str(SERVICE_STATE.get("device") or "cuda"),
        runner_kind="live_chat_service",
        service_mode="live_service",
        prompt_version=str(SERVICE_STATE.get("prompt_version") or ""),
        generation_config_version=str(SERVICE_STATE.get("generation_config_version") or "v1"),
        context_builder_version=str(SERVICE_STATE.get("context_builder_version") or "v1"),
    )
    generation_config = build_generation_config(max_new_tokens, do_sample, temperature, top_p)
    trace_meta = {
        "request_id": request_id,
        "route": route_name,
        "deployment_slug": SERVICE_STATE.get("deployment_slug"),
        "deployment_id": SERVICE_STATE.get("deployment_id"),
    }
    trace_meta.update(incoming_trace_meta)
    trace_path = build_trace_path(request_id)

    target_device = next(model.parameters()).device
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    )
    inputs = {k: v.to(target_device) for k, v in inputs.items()}
    prompt_tokens = int(inputs["input_ids"].shape[-1])

    return {
        "request_id": request_id,
        "tokenizer": tokenizer,
        "model": model,
        "messages": messages,
        "inputs": inputs,
        "prompt_tokens": prompt_tokens,
        "generation": generation_config,
        "runtime_signature": runtime_signature,
        "trace_meta": trace_meta,
        "trace_path": trace_path,
        "max_new_tokens": max_new_tokens,
        "do_sample": do_sample,
        "temperature": temperature,
        "top_p": top_p,
    }


def stream_response_events(payload: dict, route_name: str = "chat"):
    context = prepare_generation(payload, route_name)
    tokenizer = context["tokenizer"]
    model = context["model"]
    inputs = context["inputs"]
    prompt_tokens = context["prompt_tokens"]
    max_new_tokens = context["max_new_tokens"]
    do_sample = context["do_sample"]
    temperature = context["temperature"]
    top_p = context["top_p"]
    generation_config = context["generation"]
    runtime_signature = context["runtime_signature"]
    trace_meta = context["trace_meta"]
    trace_path = context["trace_path"]

    yield {
        "type": "meta",
        "request_id": context["request_id"],
        "trace_path": str(trace_path),
        "runtime_signature": runtime_signature,
        "generation": generation_config,
        "request": build_inference_request(
            context["messages"],
            generation_config,
            trace_meta,
            runtime_signature,
        ),
        "trace_meta": trace_meta,
        "prompt_tokens": prompt_tokens,
        "max_new_tokens": max_new_tokens,
        "messages": context["messages"],
    }

    input_ids = inputs["input_ids"]
    attention_mask = inputs.get("attention_mask")
    if attention_mask is None:
        attention_mask = torch.ones_like(input_ids)

    eos_token_ids = []
    if tokenizer.eos_token_id is None:
        eos_token_ids = []
    elif isinstance(tokenizer.eos_token_id, int):
        eos_token_ids = [tokenizer.eos_token_id]
    else:
        eos_token_ids = list(tokenizer.eos_token_id)

    generated_tokens = []
    raw_output_text = ""
    clean_output_text = ""
    started = time.time()
    autocast_dtype = next(model.parameters()).dtype
    use_autocast = input_ids.device.type == "cuda" and autocast_dtype in {torch.float16, torch.bfloat16}
    step_input_ids = input_ids
    past_key_values = None

    with MODEL_BUNDLE["generate_lock"]:
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
            next_token = pick_next_token(
                next_token_logits,
                do_sample=do_sample,
                temperature=temperature,
                top_p=top_p,
            )
            generated_tokens.append(next_token)
            token_text = tokenizer.decode(next_token[0], skip_special_tokens=False)
            raw_output_text += token_text
            next_clean_text = clean_output(raw_output_text)
            if next_clean_text.startswith(clean_output_text):
                delta = next_clean_text[len(clean_output_text):]
            else:
                delta = next_clean_text
            clean_output_text = next_clean_text

            step_input_ids = next_token
            attention_mask = torch.cat(
                [
                    attention_mask,
                    torch.ones((attention_mask.shape[0], 1), dtype=attention_mask.dtype, device=attention_mask.device),
                ],
                dim=-1,
            )

            if delta:
                yield {
                    "type": "chunk",
                    "delta": delta,
                    "generated_tokens": len(generated_tokens),
                }

            if eos_token_ids and int(next_token.item()) in eos_token_ids:
                break

    latency_ms = int((time.time() - started) * 1000)
    if generated_tokens:
        new_tokens = torch.cat(generated_tokens, dim=-1)
    else:
        new_tokens = input_ids[:, 0:0]

    trace_record = {
        "kind": "persona_live_request_trace_v1",
        "request_id": context["request_id"],
        "runtime_signature": runtime_signature,
        "request": build_inference_request(
            context["messages"],
            generation_config,
            trace_meta,
            runtime_signature,
        ),
        "response": {
            "raw_output_text": raw_output_text,
            "output_text": clean_output_text,
            "generated_tokens": int(new_tokens.shape[-1]),
            "prompt_tokens": prompt_tokens,
            "latency_ms": latency_ms,
            "contains_control_tokens": bool(CONTROL_TOKEN_RE.search(raw_output_text)),
            "blank_output": not clean_output_text.strip(),
            "short_output": len(clean_output_text) < 30,
        },
        "metrics": {
            "prompt_tokens": prompt_tokens,
            "generated_tokens": int(new_tokens.shape[-1]),
            "latency_ms": latency_ms,
        },
        "artifacts": {
            "trace_path": str(trace_path),
            "trace_dir": str(trace_path.parent),
        },
    }
    try:
        write_trace_artifact(trace_path, trace_record)
    except Exception as error:
        trace_record["trace_write_error"] = str(error)

    yield {
        "type": "done",
        "request_id": context["request_id"],
        "trace_path": str(trace_path),
        "runtime_signature": runtime_signature,
        "generation": generation_config,
        "request": build_inference_request(
            context["messages"],
            generation_config,
            trace_meta,
            runtime_signature,
        ),
        "trace_meta": trace_meta,
        "messages": context["messages"],
        "prompt_tokens": prompt_tokens,
        "generated_tokens": int(new_tokens.shape[-1]),
        "latency_ms": latency_ms,
        "raw_output_text": raw_output_text,
        "output_text": clean_output_text,
        "contains_control_tokens": bool(CONTROL_TOKEN_RE.search(raw_output_text)),
        "blank_output": not clean_output_text.strip(),
        "short_output": len(clean_output_text) < 30,
        "trace": trace_record,
    }


def generate_response(payload: dict) -> dict:
    final_result = None
    for event in stream_response_events(payload, route_name="chat"):
        if event.get("type") == "done":
            final_result = dict(event)
    if final_result is None:
        raise RuntimeError("generation produced no final result")
    final_result.pop("type", None)
    return final_result


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonaLiveInfer/0.1"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_sse_headers(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _write_sse(self, payload: dict):
        body = ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, fmt, *args):
        print(f"http {self.address_string()} {fmt % args}", flush=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload = {
                "ready": SERVICE_STATE["ready"],
                "loading": SERVICE_STATE["loading"],
                "error": SERVICE_STATE["error"],
                "deployment_id": SERVICE_STATE["deployment_id"],
                "deployment_slug": SERVICE_STATE["deployment_slug"],
                "base_model_path": SERVICE_STATE["base_model_path"],
                "adapter_path": SERVICE_STATE["adapter_path"],
                "system_prompt_file": SERVICE_STATE["system_prompt_file"],
                "device": SERVICE_STATE["device"],
                "prompt_version": SERVICE_STATE["prompt_version"],
                "generation_config_version": SERVICE_STATE["generation_config_version"],
                "context_builder_version": SERVICE_STATE["context_builder_version"],
                "default_max_new_tokens": SERVICE_STATE["default_max_new_tokens"],
                "kv_cache_enabled": True,
                "trace_dir": SERVICE_STATE["trace_dir"],
                "uptime_sec": int(time.time() - SERVICE_STATE["started_at"]),
            }
            self._send_json(payload)
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/chat":
            try:
                payload = self._read_json()
                result = generate_response(payload)
                self._send_json(result)
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/stream":
            try:
                payload = self._read_json()
            except ValueError as error:
                self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                self._send_sse_headers()
                for event in stream_response_events(payload, route_name="stream"):
                    self._write_sse(event)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                try:
                    self._write_sse({"type": "error", "error": str(error)})
                except (BrokenPipeError, ConnectionResetError):
                    pass
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)


class SafeThreadingHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # Avoid HTTPServer.getfqdn(), which can fail on stripped Python envs
        # that are otherwise still able to serve requests normally.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--base-model-path", required=True)
    parser.add_argument("--adapter-path", default="")
    parser.add_argument("--system-prompt-file", default="")
    parser.add_argument("--deployment-id", default="")
    parser.add_argument("--deployment-slug", default="")
    parser.add_argument("--prompt-version", default="")
    parser.add_argument("--generation-config-version", default="v1")
    parser.add_argument("--context-builder-version", default="v1")
    parser.add_argument("--trace-dir", default="")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--max-new-tokens-default", type=int, default=256)
    args = parser.parse_args()

    default_trace_dir = args.trace_dir or str(
        Path.cwd()
        / "runtime_logs"
        / "live"
        / sanitize_artifact_name(args.deployment_slug or Path(args.base_model_path).stem or "live")
        / "traces"
    )
    SERVICE_STATE.update(
        {
            "deployment_id": args.deployment_id or None,
            "deployment_slug": args.deployment_slug or None,
            "base_model_path": args.base_model_path,
            "adapter_path": args.adapter_path or None,
            "system_prompt_file": args.system_prompt_file or None,
            "device": args.device,
            "prompt_version": args.prompt_version or resolve_prompt_version(args.system_prompt_file),
            "generation_config_version": args.generation_config_version,
            "context_builder_version": args.context_builder_version,
            "default_max_new_tokens": args.max_new_tokens_default,
            "trace_dir": default_trace_dir,
        }
    )

    try:
        tokenizer, model, default_system_prompt = build_model(
            args.base_model_path,
            args.adapter_path,
            args.system_prompt_file,
            args.device,
        )
        MODEL_BUNDLE["tokenizer"] = tokenizer
        MODEL_BUNDLE["model"] = model
        MODEL_BUNDLE["default_system_prompt"] = default_system_prompt
        SERVICE_STATE["ready"] = True
        SERVICE_STATE["loading"] = False
        print(
            f"service_ready host={args.host} port={args.port} device={args.device} base={args.base_model_path} adapter={args.adapter_path or '-'}",
            flush=True,
        )
    except Exception as error:
        SERVICE_STATE["error"] = str(error)
        SERVICE_STATE["loading"] = False
        print(f"service_failed error={error}", flush=True)
        raise

    server = SafeThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
