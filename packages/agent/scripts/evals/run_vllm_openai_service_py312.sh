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

REPO_ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
VLLM_ROOT="${PERSONA_VLLM_ROOT:-${HOME:-/root}/yueyu}"
VENV_ROOT="${PERSONA_VLLM_VENV:-$VLLM_ROOT/.venv_vllm}"
CACHE_ROOT="${PERSONA_VLLM_CACHE_ROOT:-$VLLM_ROOT/.cache/ququ_vllm}"
CONFIG_ROOT="${PERSONA_VLLM_CONFIG_ROOT:-$VLLM_ROOT/.config/ququ_vllm}"
TMP_ROOT="${PERSONA_VLLM_TMP_ROOT:-$VLLM_ROOT/.tmp/ququ_vllm}"
VLLM_BIN="${VLLM_BIN:-$VENV_ROOT/bin/vllm}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_ROOT/bin/python3}"

if [[ ! -x "$VLLM_BIN" ]]; then
  echo "vllm binary not found: $VLLM_BIN" >&2
  exit 1
fi

BASE_MODEL_PATH=""
ADAPTER_PATH=""
DEPLOYMENT_ID=""
DEPLOYMENT_SLUG=""
TRACE_DIR=""
DEVICE="cuda"
MAX_NEW_TOKENS_DEFAULT="256"
SYSTEM_PROMPT_FILE=""
VLLM_LANGUAGE_MODEL_ONLY="${VLLM_LANGUAGE_MODEL_ONLY:-1}"
VLLM_ENFORCE_EAGER="${VLLM_ENFORCE_EAGER:-1}"
VLLM_ENABLE_PREFIX_CACHING="${VLLM_ENABLE_PREFIX_CACHING:-0}"
VLLM_GDN_PREFILL_BACKEND="${VLLM_GDN_PREFILL_BACKEND:-triton}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-model-path)
      BASE_MODEL_PATH=$2
      shift 2
      ;;
    --adapter-path)
      ADAPTER_PATH=$2
      shift 2
      ;;
    --deployment-id)
      DEPLOYMENT_ID=$2
      shift 2
      ;;
    --deployment-slug)
      DEPLOYMENT_SLUG=$2
      shift 2
      ;;
    --device)
      DEVICE=$2
      shift 2
      ;;
    --max-new-tokens-default)
      MAX_NEW_TOKENS_DEFAULT=$2
      shift 2
      ;;
    --system-prompt-file)
      SYSTEM_PROMPT_FILE=$2
      shift 2
      ;;
    --trace-dir)
      TRACE_DIR=$2
      shift 2
      ;;
    --prompt-version|--generation-config-version|--context-builder-version)
      shift 2
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$BASE_MODEL_PATH" ]]; then
  echo "--base-model-path is required" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_PATH")" "$(dirname "$STATUS_PATH")" "$CACHE_ROOT" "$CONFIG_ROOT" "$TMP_ROOT"
if [[ -n "$TRACE_DIR" ]]; then
  mkdir -p "$TRACE_DIR"
fi

cd "$REPO_ROOT"

export PYTHONUNBUFFERED=1
export HF_HOME="$CACHE_ROOT/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export XDG_CACHE_HOME="$CACHE_ROOT"
export XDG_CONFIG_HOME="$CONFIG_ROOT"
export PIP_CACHE_DIR="$CACHE_ROOT/pip"
export PATH="$VENV_ROOT/bin:$PATH"
export TMPDIR="$TMP_ROOT"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export HOME="$VLLM_ROOT"
export TOKENIZERS_PARALLELISM=false
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_NO_USAGE_STATS=1
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

if [[ "$DEVICE" != "cuda" ]]; then
  echo "Only cuda device is supported for vLLM service right now" >&2
  exit 1
fi

BASE_MODEL_NAME="${DEPLOYMENT_SLUG:-${DEPLOYMENT_ID:-persona-model}}-base"
LORA_NAME="${DEPLOYMENT_SLUG:-${DEPLOYMENT_ID:-persona-lora}}"
CHAT_TEMPLATE_FILE=""
if [[ -n "$ADAPTER_PATH" && -f "$ADAPTER_PATH/chat_template.jinja" ]]; then
  CHAT_TEMPLATE_FILE="$ADAPTER_PATH/chat_template.jinja"
fi

CMD=(
  "$VLLM_BIN"
  serve
  "$BASE_MODEL_PATH"
  --host "$LISTEN_HOST"
  --port "$LISTEN_PORT"
  --served-model-name "$BASE_MODEL_NAME"
  --dtype "${VLLM_DTYPE:-half}"
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.92}"
  --max-model-len "${VLLM_MAX_MODEL_LEN:-16384}"
  --max-num-seqs "${VLLM_MAX_NUM_SEQS:-4}"
  --max-log-len "${VLLM_MAX_LOG_LEN:-64}"
  --generation-config vllm
  --trust-remote-code
)

if [[ "$VLLM_LANGUAGE_MODEL_ONLY" == "1" ]]; then
  CMD+=(--language-model-only)
fi

if [[ "$VLLM_ENFORCE_EAGER" == "1" ]]; then
  CMD+=(--enforce-eager)
fi

if [[ "$VLLM_ENABLE_PREFIX_CACHING" == "1" ]]; then
  CMD+=(--enable-prefix-caching)
fi

if [[ -n "$VLLM_GDN_PREFILL_BACKEND" ]]; then
  CMD+=(--gdn-prefill-backend "$VLLM_GDN_PREFILL_BACKEND")
fi

if [[ -n "$CHAT_TEMPLATE_FILE" ]]; then
  CMD+=(--chat-template "$CHAT_TEMPLATE_FILE")
fi

if [[ -n "$ADAPTER_PATH" ]]; then
  CMD+=(
    --enable-lora
    --max-lora-rank "${VLLM_MAX_LORA_RANK:-64}"
    --lora-modules "${LORA_NAME}=${ADAPTER_PATH}"
  )
fi

{
  echo "__START__ $(date -Is)"
  echo "__VLLM__ $VLLM_BIN"
  echo "__PYTHON__ $PYTHON_BIN"
  echo "__NINJA__ $(command -v ninja || echo missing)"
  echo "__VLLM_ROOT__ $VLLM_ROOT"
  echo "__VENV_ROOT__ $VENV_ROOT"
  echo "__CACHE_ROOT__ $CACHE_ROOT"
  echo "__CONFIG_ROOT__ $CONFIG_ROOT"
  echo "__TMP_ROOT__ $TMP_ROOT"
  echo "__BASE_MODEL__ $BASE_MODEL_PATH"
  echo "__ADAPTER__ ${ADAPTER_PATH:--}"
  echo "__DEPLOYMENT_SLUG__ ${DEPLOYMENT_SLUG:--}"
  echo "__MAX_NEW_TOKENS_DEFAULT__ $MAX_NEW_TOKENS_DEFAULT"
  echo "__SYSTEM_PROMPT_FILE__ ${SYSTEM_PROMPT_FILE:--}"
  echo "__VLLM_LANGUAGE_MODEL_ONLY__ $VLLM_LANGUAGE_MODEL_ONLY"
  echo "__VLLM_ENFORCE_EAGER__ $VLLM_ENFORCE_EAGER"
  echo "__VLLM_ENABLE_PREFIX_CACHING__ $VLLM_ENABLE_PREFIX_CACHING"
  echo "__VLLM_GDN_PREFILL_BACKEND__ $VLLM_GDN_PREFILL_BACKEND"
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
