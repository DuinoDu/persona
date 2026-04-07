#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

mkdir -p runtime_logs third_party scripts/sft configs/llamafactory artifacts/llamafactory_data outputs .pkg

if [[ ! -d third_party/LLaMA-Factory/.git ]]; then
  git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git third_party/LLaMA-Factory
else
  git -C third_party/LLaMA-Factory pull --ff-only
fi

PY_VER=$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
PKG_ROOT="$REPO_ROOT/.pkg"
SITE_PACKAGES="$PKG_ROOT/lib/python${PY_VER}/site-packages"
BIN_DIR="$PKG_ROOT/bin"
mkdir -p "$PKG_ROOT"

python3 -m pip install --upgrade --prefix "$PKG_ROOT" pip setuptools wheel
python3 -m pip install --prefix "$PKG_ROOT" --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1+cu121
python3 -m pip install --prefix "$PKG_ROOT" "$REPO_ROOT/third_party/LLaMA-Factory"

export PATH="$BIN_DIR:$PATH"
export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
python3 - <<'PY'
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
print('device_count', torch.cuda.device_count())
if torch.cuda.is_available():
    print('device_name', torch.cuda.get_device_name(0))
PY
