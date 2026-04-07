#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_base_model_path(ckpt_dir: Path, override: str | None) -> str:
    if override:
        return override
    cfg = json.loads((ckpt_dir / 'adapter_config.json').read_text(encoding='utf-8'))
    return cfg['base_model_name_or_path']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint-dir', required=True)
    parser.add_argument('--base-model-path', default='')
    parser.add_argument('--system-prompt-file', default='')
    parser.add_argument('--user-text', required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--max-new-tokens', type=int, default=256)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    args = parser.parse_args()

    ckpt_dir = Path(args.checkpoint_dir)
    output_json = Path(args.output_json)
    base_model_path = load_base_model_path(ckpt_dir, args.base_model_path or None)
    attn_implementation = os.getenv('PERSONA_ATTN_IMPLEMENTATION', '') or 'eager'
    device = args.device
    disable_fla = os.getenv('PERSONA_DISABLE_FLA', '0') == '1'
    disable_causal_conv1d = os.getenv('PERSONA_DISABLE_CAUSAL_CONV1D', '0') == '1'
    if disable_fla or disable_causal_conv1d:
        import sys
        from transformers.utils import import_utils as hf_import_utils
        if disable_fla:
            hf_import_utils.is_flash_linear_attention_available = lambda: False
        if disable_causal_conv1d:
            hf_import_utils.is_causal_conv1d_available = lambda: False
        for mod_name in list(sys.modules):
            if mod_name.startswith('transformers.models.qwen3_5'):
                del sys.modules[mod_name]

    system_prompt = ''
    if args.system_prompt_file:
        system_prompt = Path(args.system_prompt_file).read_text(encoding='utf-8')

    print(f'stage=load_tokenizer base_model_path={base_model_path}', flush=True)
    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)

    print(f'stage=load_base_model attn_implementation={attn_implementation} device={device}', flush=True)
    load_kwargs = dict(
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation=attn_implementation,
    )
    if device == 'cuda':
        load_kwargs['device_map'] = {'': 0}
    model = AutoModelForCausalLM.from_pretrained(base_model_path, **load_kwargs)
    if device == 'cpu':
        model.to('cpu')

    print(f'stage=load_adapter checkpoint={ckpt_dir}', flush=True)
    model = PeftModel.from_pretrained(model, str(ckpt_dir))
    if device == 'cpu':
        model.to('cpu')
    model.eval()
    if hasattr(model, 'config'):
        model.config.use_cache = False

    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': args.user_text})

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors='pt',
        return_dict=True,
    )
    target_device = next(model.parameters()).device
    inputs = {k: v.to(target_device) for k, v in inputs.items()}
    prompt_tokens = int(inputs['input_ids'].shape[-1])
    print(f'prompt_tokens={prompt_tokens}', flush=True)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=False,
        )

    new_tokens = outputs[0, inputs['input_ids'].shape[-1]:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=False)

    print('=== MODEL OUTPUT BEGIN ===', flush=True)
    print(text, flush=True)
    print('=== MODEL OUTPUT END ===', flush=True)

    result = {
        'checkpoint_dir': str(ckpt_dir),
        'base_model_path': base_model_path,
        'system_prompt_file': args.system_prompt_file,
        'user_text': args.user_text,
        'prompt_tokens': prompt_tokens,
        'generated_tokens': int(new_tokens.shape[-1]),
        'output_text': text,
    }
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'saved_json={output_json}', flush=True)


if __name__ == '__main__':
    main()
