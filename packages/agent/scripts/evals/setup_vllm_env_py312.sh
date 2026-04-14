#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
VLLM_ROOT="${PERSONA_VLLM_ROOT:-${HOME:-/root}/yueyu}"
VENV_ROOT="${PERSONA_VLLM_VENV:-$VLLM_ROOT/.venv_vllm}"
CACHE_ROOT="${PERSONA_VLLM_CACHE_ROOT:-$VLLM_ROOT/.cache/ququ_vllm}"
CONFIG_ROOT="${PERSONA_VLLM_CONFIG_ROOT:-$VLLM_ROOT/.config/ququ_vllm}"
TMP_ROOT="${PERSONA_VLLM_TMP_ROOT:-$VLLM_ROOT/.tmp/ququ_vllm}"
PYTHON_CANDIDATES=(
  "${PYTHON_BIN:-}"
  "$VLLM_ROOT/dot_rye/py/cpython@3.12.9/bin/python3.12"
  "$VLLM_ROOT/dot_rye/py/cpython@3.12.9/bin/python3"
  "$REPO_ROOT/.venv/bin/python3.12"
  "$REPO_ROOT/.venv/bin/python3"
  "$REPO_ROOT/.localbin/python3"
  "$(command -v python3.12 || true)"
  "$(command -v python3 || true)"
)
PYTHON_BIN=""
for candidate in "${PYTHON_CANDIDATES[@]}"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "python binary not found" >&2
  exit 1
fi

mkdir -p "$CACHE_ROOT" "$CONFIG_ROOT" "$TMP_ROOT"
export HOME="$VLLM_ROOT"
export TMPDIR="$TMP_ROOT"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export XDG_CACHE_HOME="$CACHE_ROOT"
export XDG_CONFIG_HOME="$CONFIG_ROOT"
export PIP_CACHE_DIR="$CACHE_ROOT/pip"
export HF_HOME="$CACHE_ROOT/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"

echo "__VLLM_ROOT__ $VLLM_ROOT"
echo "__VENV_ROOT__ $VENV_ROOT"
echo "__CACHE_ROOT__ $CACHE_ROOT"
echo "__CONFIG_ROOT__ $CONFIG_ROOT"
echo "__TMP_ROOT__ $TMP_ROOT"

if [[ ! -x "$VENV_ROOT/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi

"$VENV_ROOT/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_ROOT/bin/pip" install vllm

"$VENV_ROOT/bin/python" - <<'PY'
import importlib.util
spec = importlib.util.find_spec("vllm")
print(f"vllm_spec={spec}")
PY
