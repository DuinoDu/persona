#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <log_path> <status_path> <host> <port> [service_args...]" >&2
  exit 1
fi

LOG_PATH=$1
STATUS_PATH=$2
LISTEN_HOST=$3
LISTEN_PORT=$4
shift 4

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.localbin/python3}
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python binary not found: $PYTHON_BIN" >&2
  exit 1
fi

PY_VER=$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
SITE_PACKAGES="$REPO_ROOT/.pkg/lib/python${PY_VER}/site-packages"
BIN_DIR="$REPO_ROOT/.pkg/bin"

mkdir -p "$(dirname "$LOG_PATH")" "$(dirname "$STATUS_PATH")" "$REPO_ROOT/.cache/triton" "$REPO_ROOT/.cache/torchinductor" "$REPO_ROOT/.cache/torch_extensions" "$REPO_ROOT/.tmp"
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
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export PYTHONFAULTHANDLER="${PYTHONFAULTHANDLER:-1}"
export PERSONA_DISABLE_FLA="${PERSONA_DISABLE_FLA:-1}"
export PERSONA_DISABLE_CAUSAL_CONV1D="${PERSONA_DISABLE_CAUSAL_CONV1D:-1}"
export PERSONA_ATTN_IMPLEMENTATION="${PERSONA_ATTN_IMPLEMENTATION:-eager}"

SCRIPT_PATH="$REPO_ROOT/scripts/evals/live_chat_service_qwen35_9b.py"
CMD=("$PYTHON_BIN" -u "$SCRIPT_PATH" --host "$LISTEN_HOST" --port "$LISTEN_PORT" "$@")

{
  echo "__START__ $(date -Is)"
  echo "__PYTHON__ $PYTHON_BIN"
  printf '__CMD__'; printf ' %q' "${CMD[@]}"; echo
} | tee -a "$LOG_PATH"

set +e
set -o pipefail
"${CMD[@]}" 2>&1 | tee -a "$LOG_PATH"
EC=${PIPESTATUS[0]}
set -e

echo "$EC" > "$STATUS_PATH"
echo "__EXIT_CODE__=$EC __TIME__=$(date -Is)" | tee -a "$LOG_PATH"
exit "$EC"
