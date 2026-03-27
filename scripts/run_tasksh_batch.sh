#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/duino/ws/ququ/process_youtube"
TASK_FILE="$ROOT/task.sh"
PPL_DIR="/home/duino/ws/ququ/ppl"
MAX_CONCURRENT=4
TIMEOUT_SECONDS=$((60 * 60))

source "$TASK_FILE" >/dev/null

if [[ -z "${data:-}" || -z "${ai:-}" ]]; then
  echo "task.sh did not define required vars: data / ai" >&2
  exit 1
fi

cd "$ROOT"

mapfile -d '' FILES < <(find "$data" -maxdepth 1 -type f -name '*.json' -print0 | sort -z)
TOTAL_ALL=${#FILES[@]}
if (( skip > TOTAL_ALL )); then
  echo "skip=$skip exceeds total file count=$TOTAL_ALL" >&2
  exit 1
fi
FILES=("${FILES[@]:skip}")
TOTAL=${#FILES[@]}

RUN_ID="$(basename "$data" | tr ' /' '__')_$(date +%Y%m%d_%H%M%S)"
STATE_DIR="$ROOT/logs/task_runs/$RUN_ID"
TASK_DIR="$STATE_DIR/tasks"
mkdir -p "$TASK_DIR"

MANIFEST="$STATE_DIR/manifest.tsv"
STATUS="$STATE_DIR/status.tsv"
CONTROLLER_LOG="$STATE_DIR/controller.log"
: > "$MANIFEST"
: > "$STATUS"

printf 'run_id\t%s\n' "$RUN_ID" | tee -a "$CONTROLLER_LOG"
printf 'data\t%s\n' "$data" | tee -a "$CONTROLLER_LOG"
printf 'skip\t%s\n' "$skip" | tee -a "$CONTROLLER_LOG"
printf 'total_after_skip\t%s\n' "$TOTAL" | tee -a "$CONTROLLER_LOG"
printf 'ai\t%s\n' "$ai" | tee -a "$CONTROLLER_LOG"
printf 'state_dir\t%s\n' "$STATE_DIR" | tee -a "$CONTROLLER_LOG"

session_name_for() {
  local idx="$1"
  printf 'ququ_%s_%03d' "$RUN_ID" "$idx"
}

running_count() {
  tmux ls 2>/dev/null | awk -F: -v p="ququ_${RUN_ID}_" '$1 ~ ("^" p) {c++} END {print c+0}'
}

for i in "${!FILES[@]}"; do
  idx=$((i + 1))
  json_file="${FILES[$i]}"
  session_name="$(session_name_for "$idx")"
  task_script="$TASK_DIR/${idx}.sh"
  task_log="$TASK_DIR/${idx}.log"
  printf '%s\t%s\t%s\t%s\n' "$idx" "$session_name" queued "$json_file" >> "$MANIFEST"

  cat > "$task_script" <<TASK
#!/usr/bin/env bash
set -euo pipefail
cd "$PPL_DIR"
export AI=$(printf '%q' "$ai")
export JSON_FILE=$(printf '%q' "$json_file")
prompt="\$(bash prompt.sh)"
eval "$ai \"\$prompt\""
TASK
  chmod +x "$task_script"

  while (( $(running_count) >= MAX_CONCURRENT )); do
    sleep 10
  done

  printf '%s\t%s\tlaunched\t%s\t%s\n' "$(date '+%F %T')" "$idx" "$session_name" "$json_file" | tee -a "$STATUS" "$CONTROLLER_LOG"
  tmux new-session -d -s "$session_name" "timeout --signal=TERM --kill-after=30s ${TIMEOUT_SECONDS}s bash '$task_script' > '$task_log' 2>&1"
done

printf '%s\tall_launched\t%s\n' "$(date '+%F %T')" "$TOTAL" | tee -a "$STATUS" "$CONTROLLER_LOG"

while (( $(running_count) > 0 )); do
  sleep 15
done

printf '%s\tall_finished\t%s\n' "$(date '+%F %T')" "$TOTAL" | tee -a "$STATUS" "$CONTROLLER_LOG"
