#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <config.yaml>" >&2
  exit 1
fi

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CONFIG_PATH=$1
shift || true
PY_VER=$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
PKG_ROOT="$REPO_ROOT/.pkg"
SITE_PACKAGES="$PKG_ROOT/lib/python${PY_VER}/site-packages"
BIN_DIR="$PKG_ROOT/bin"

cd "$REPO_ROOT"
export PATH="$BIN_DIR:$PATH"
export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
export HF_HOME="$REPO_ROOT/.cache/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export XDG_CACHE_HOME="$REPO_ROOT/.cache"
export TOKENIZERS_PARALLELISM=false
export DISABLE_VERSION_CHECK=1

llamafactory-cli train "$CONFIG_PATH" "$@"
