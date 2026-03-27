#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_DIR="${INPUT_DIR:-$ROOT_DIR/data/02_audio_splits}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/speech2text/.venv/bin/python}"
S2T_ROOT="${S2T_ROOT:-$ROOT_DIR/speech2text}"
CHUNK_MINUTES="${CHUNK_MINUTES:-30}"

TRANSCRIBE_ARGS_DEFAULT=(
  --min-speakers 2
  --max-speakers 4
)

EXTRA_ARGS=()
if [[ $# -gt 0 ]]; then
  EXTRA_ARGS=("$@")
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found or not executable: $PYTHON_BIN" >&2; exit 1
fi

if [[ ! -d "$S2T_ROOT" ]]; then
  echo "speech2text root not found: $S2T_ROOT" >&2; exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "Input directory not found: $INPUT_DIR" >&2; exit 1
fi

mapfile -d '' mp3s < <(find "$INPUT_DIR" -type f -name "*.mp3" ! -name "*_30min.mp3" -print0 | LC_ALL=C sort -z)
total=${#mp3s[@]}
if [[ $total -eq 0 ]]; then
  echo "No mp3 files found under $INPUT_DIR" >&2; exit 1
fi

echo "Found $total MP3 files under $INPUT_DIR"

index=0
for mp3 in "${mp3s[@]}"; do
  index=$((index + 1))
  json="${mp3%.mp3}.json"
  if [[ -s "$json" ]]; then
    echo "[$index/$total] Skip (exists): $json"
    continue
  fi

  echo "[$index/$total] Processing: $mp3"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/03_split_transcribe_merge.py" \
    "$mp3" \
    --chunk-minutes "$CHUNK_MINUTES" \
    --python "$PYTHON_BIN" \
    --speech2text-root "$S2T_ROOT" \
    -- "${TRANSCRIBE_ARGS_DEFAULT[@]}" "${EXTRA_ARGS[@]}" || echo "[$index/$total] FAILED: $mp3"
done
echo "All done."
