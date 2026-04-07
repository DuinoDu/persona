#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.localbin/python3}
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python binary not found: $PYTHON_BIN" >&2
  exit 1
fi

mkdir -p runtime_logs third_party scripts/sft configs/llamafactory artifacts/llamafactory_data outputs .pkg .cache .cache/triton .cache/torchinductor .cache/torch_extensions .localbin .tmp

export PYTHONUNBUFFERED=1
export HF_HOME="$REPO_ROOT/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export XDG_CACHE_HOME="$REPO_ROOT/.cache"
export PIP_CACHE_DIR="$REPO_ROOT/.cache/pip"
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cu121"
export PIP_DEFAULT_TIMEOUT="1200"
export PIP_DISABLE_PIP_VERSION_CHECK="1"
export TMPDIR="$REPO_ROOT/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export TRITON_CACHE_DIR="$REPO_ROOT/.cache/triton"
export TORCHINDUCTOR_CACHE_DIR="$REPO_ROOT/.cache/torchinductor"
export TORCH_EXTENSIONS_DIR="$REPO_ROOT/.cache/torch_extensions"
export TOKENIZERS_PARALLELISM=false
export DISABLE_VERSION_CHECK=1

PY_VER=$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
PKG_ROOT="$REPO_ROOT/.pkg"
SITE_PACKAGES="$PKG_ROOT/lib/python${PY_VER}/site-packages"
BIN_DIR="$PKG_ROOT/bin"
BOOTSTRAP_PIP_SITE=""

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  BOOTSTRAP_ROOT="$REPO_ROOT/.tmp/ensurepip-root"
  rm -rf "$BOOTSTRAP_ROOT"
  mkdir -p "$BOOTSTRAP_ROOT"
  "$PYTHON_BIN" -m ensurepip --root "$BOOTSTRAP_ROOT" --default-pip >/dev/null
  BOOTSTRAP_PIP_SITE=$(find "$BOOTSTRAP_ROOT" -type d -path '*/site-packages' | head -n 1)
  if [[ -z "$BOOTSTRAP_PIP_SITE" ]]; then
    echo "failed to bootstrap pip into $BOOTSTRAP_ROOT" >&2
    exit 1
  fi
fi

if [[ -n "$BOOTSTRAP_PIP_SITE" ]]; then
  export PYTHONPATH="$BOOTSTRAP_PIP_SITE:$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
else
  export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
fi
export PATH="$BIN_DIR:$PATH"

"$PYTHON_BIN" -m pip install --prefix "$PKG_ROOT" torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121
"$PYTHON_BIN" -m pip install --prefix "$PKG_ROOT" --no-deps triton==3.2.0
"$PYTHON_BIN" -m pip install --prefix "$PKG_ROOT" -r "$REPO_ROOT/third_party/LLaMA-Factory/requirements/bitsandbytes.txt"
"$PYTHON_BIN" -m pip install --prefix "$PKG_ROOT" "$REPO_ROOT/third_party/LLaMA-Factory"
"$PYTHON_BIN" -m pip install --prefix "$PKG_ROOT" --no-deps fla-core==0.4.2 flash-linear-attention==0.4.2

"$PYTHON_BIN" - <<'PY'
import bitsandbytes as bnb
import importlib.util
import torch
import triton
import transformers
import datasets
import peft
import trl
print('python', __import__('sys').version)
print('torch', torch.__version__)
print('triton', triton.__version__)
print('cuda_available', torch.cuda.is_available())
print('device_count', torch.cuda.device_count())
if torch.cuda.is_available():
    print('device_name', torch.cuda.get_device_name(0))
print('transformers', transformers.__version__)
print('datasets', datasets.__version__)
print('peft', peft.__version__)
print('trl', trl.__version__)
print('bitsandbytes', bnb.__version__)
print('fla_available', bool(importlib.util.find_spec('fla')))
PY
