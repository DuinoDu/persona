#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <config.yaml> [extra_args...]" >&2
  exit 1
fi

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CONFIG_PATH=$1
shift || true
PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python3}
PY_VER=$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
PKG_ROOT="$REPO_ROOT/.pkg"
SITE_PACKAGES="$PKG_ROOT/lib/python${PY_VER}/site-packages"
BIN_DIR="$PKG_ROOT/bin"

if [[ ! -x "$BIN_DIR/llamafactory-cli" ]]; then
  echo "llamafactory-cli not found in $BIN_DIR. Run setup_h20_env_py312.sh first." >&2
  exit 1
fi

cd "$REPO_ROOT"
export PATH="$BIN_DIR:$PATH"
export PYTHONPATH="$REPO_ROOT:$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
export HF_HOME="$REPO_ROOT/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export XDG_CACHE_HOME="$REPO_ROOT/.cache"
export PIP_CACHE_DIR="$REPO_ROOT/.cache/pip"
export TMPDIR="$REPO_ROOT/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export TRITON_CACHE_DIR="$REPO_ROOT/.cache/triton"
export TORCHINDUCTOR_CACHE_DIR="$REPO_ROOT/.cache/torchinductor"
export TORCH_EXTENSIONS_DIR="$REPO_ROOT/.cache/torch_extensions"
export TOKENIZERS_PARALLELISM=false
export DISABLE_VERSION_CHECK=1
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

mkdir -p "$TRITON_CACHE_DIR" "$TORCHINDUCTOR_CACHE_DIR" "$TORCH_EXTENSIONS_DIR"

llamafactory-cli train "$CONFIG_PATH" "$@"
