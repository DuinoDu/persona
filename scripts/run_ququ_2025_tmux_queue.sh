#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="/home/duino/ws/ququ/process_youtube/data/03_transcripts/曲曲2025（全）"
PPL_DIR="/home/duino/ws/ququ/ppl"
PROMPT='"719451(bash prompt.sh)"'
MAX_CONCURRENT=4
JOB_TIMEOUT=1800
SESSION_TAG="ququ2025_$(date +%Y%m%d_%H%M%S)"
LOG_DIR="/home/duino/ws/ququ/process_youtube/logs/${SESSION_TAG}"
mkdir -p "$LOG_DIR"

mapfile -d '' JSON_FILES < <(find "$SOURCE_DIR" -maxdepth 1 -type f -name '*.json' -print0 | sort -z)
TOTAL=${#JSON_FILES[@]}
if (( TOTAL == 0 )); then
  echo "No JSON files found in $SOURCE_DIR" >&2
  exit 1
fi

running_jobs() {
  local count=0
  local session
  while IFS= read -r session; do
    [[ -z "$session" ]] && continue
    if [[ "$session" == ${SESSION_TAG}_* ]]; then
      ((count+=1))
    fi
  done < <(tmux list-sessions -F '#S' 2>/dev/null || true)
  printf '%s\n' "$count"
}

launch_job() {
  local index="$1"
  local json_file="$2"
  local session_name
  local log_file
  printf -v session_name '%s_%03d' "$SESSION_TAG" "$index"
  printf -v log_file '%s/%03d.log' "$LOG_DIR" "$index"

  local quoted_json
  quoted_json=$(printf '%q' "$json_file")
  local quoted_ppl_dir
  quoted_ppl_dir=$(printf '%q' "$PPL_DIR")
  local quoted_prompt
  quoted_prompt=$(printf '%q' "$PROMPT")
  local quoted_log
  quoted_log=$(printf '%q' "$log_file")

  local inner_cmd="cd ${quoted_ppl_dir} && JSON_FILE=${quoted_json} timeout ${JOB_TIMEOUT} codex --dangerously-bypass-approvals-and-sandbox ${quoted_prompt}"
  local tmux_cmd="script -qefc $(printf '%q' "$inner_cmd") ${quoted_log}"

  tmux new-session -d -s "$session_name" "$tmux_cmd"
  printf '[%03d/%03d] %s\n' "$index" "$TOTAL" "$session_name -> $json_file"
}

echo "Session tag: $SESSION_TAG"
echo "Logs: $LOG_DIR"
echo "Total jobs: $TOTAL"

index=0
for json_file in "${JSON_FILES[@]}"; do
  ((index+=1))
  while (( $(running_jobs) >= MAX_CONCURRENT )); do
    sleep 5
  done
  launch_job "$index" "$json_file"
done

echo "All jobs dispatched. Active tmux sessions:"
tmux list-sessions -F '#S' 2>/dev/null | grep "^${SESSION_TAG}_" || true
echo "Use: tmux attach -t ${SESSION_TAG}_001"
