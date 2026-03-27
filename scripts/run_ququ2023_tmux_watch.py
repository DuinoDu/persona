#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_DIR = Path("/home/duino/ws/ququ/process_youtube")
DEFAULT_SOURCE_DIR = BASE_DIR / "data/03_transcripts/曲曲2023（全）"
DEFAULT_WORKDIR = BASE_DIR
DEFAULT_PROMPT_SCRIPT = BASE_DIR / "prompt.sh"
DEFAULT_TMUX_RUNS_DIR = BASE_DIR / ".tmux_runs"
DEFAULT_AI_CMD = "aiden --permission-mode agentFull --one-shot"


@dataclass
class Job:
    index: int
    json_file: str
    out_dir: str = ""
    state: str = "pending"
    attempts: int = 0
    retries: int = 0
    session_name: str | None = None
    log_file: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    last_reason: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 曲曲2023 JSON jobs in tmux with timeout, monitoring, reporting, and retry."
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--prompt-script", type=Path, default=DEFAULT_PROMPT_SCRIPT)
    parser.add_argument("--ai-cmd", default=DEFAULT_AI_CMD)
    parser.add_argument("--tmux-runs-dir", type=Path, default=DEFAULT_TMUX_RUNS_DIR)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--max-concurrent", type=int, default=4)
    parser.add_argument("--timeout-minutes", type=int, default=60)
    parser.add_argument("--kill-after-seconds", type=int, default=30)
    parser.add_argument("--overrun-grace-seconds", type=int, default=90)
    parser.add_argument("--poll-interval-seconds", type=int, default=15)
    parser.add_argument("--report-interval-seconds", type=int, default=600)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--session-prefix", default="ququ2023")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--max-files", type=int, default=0, help="0 means all files")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(
    argv: list[str],
    *,
    check: bool = False,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def session_exists(name: str) -> bool:
    return (
        subprocess.run(
            ["tmux", "has-session", "-t", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def list_panes(name: str) -> list[dict[str, str]]:
    result = run(
        ["tmux", "list-panes", "-t", name, "-F", "#{pane_dead}\t#{pane_pid}\t#{pane_current_command}"],
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    panes: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        dead, pid, current_command = (line.split("\t", 2) + ["", ""])[:3]
        panes.append(
            {
                "dead": dead,
                "pid": pid,
                "current_command": current_command,
            }
        )
    return panes


def kill_session(name: str) -> None:
    subprocess.run(
        ["tmux", "kill-session", "-t", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def parse_exit_code(log_file: Path) -> int | None:
    if not log_file.exists():
        return None
    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    matches = re.findall(r"EXIT_CODE=(\d+)", content)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def log_age_seconds(log_file: Path) -> float | None:
    if not log_file.exists():
        return None
    try:
        return max(0.0, time.time() - log_file.stat().st_mtime)
    except OSError:
        return None


def determine_out_dir(source_dir: Path, json_file: Path) -> Path:
    same_stem = source_dir / json_file.stem
    processed = source_dir / f"{json_file.stem}_processed"
    if same_stem.is_dir():
        return same_stem
    if processed.is_dir():
        return processed
    return same_stem


def out_dir_has_results(out_dir: Path) -> bool:
    if not out_dir.is_dir():
        return False
    try:
        return any(out_dir.glob("*.json"))
    except OSError:
        return False


def make_runner_script(path: Path, workdir: Path, prompt_script: Path, ai_cmd: str, dry_run: bool) -> None:
    if dry_run:
        body = f"""#!/usr/bin/env bash
set -u -o pipefail
json_file="${{1:?json_file path required}}"
out_dir="${{2:?out_dir path required}}"
cd {shlex.quote(str(workdir))}
mkdir -p "$out_dir"
printf '[START] %s JSON_FILE=%s OUT_DIR=%s\\n' "$(date -Is)" "$json_file" "$out_dir"
sleep "${{DRY_RUN_SLEEP:-2}}"
set +e
printf 'dry-run for %s\\n' "$json_file"
status=$?
set -e
printf '{{"dry_run":true,"json_file":"%s"}}\\n' "$json_file" > "$out_dir/_dry_run_result.json"
printf '[END] %s EXIT_CODE=%s JSON_FILE=%s OUT_DIR=%s\\n' "$(date -Is)" "$status" "$json_file" "$out_dir"
exit "$status"
"""
    else:
        body = f"""#!/usr/bin/env bash
set -u -o pipefail
json_file="${{1:?json_file path required}}"
out_dir="${{2:?out_dir path required}}"
cd {shlex.quote(str(workdir))}
mkdir -p "$out_dir"
printf '[START] %s JSON_FILE=%s OUT_DIR=%s\\n' "$(date -Is)" "$json_file" "$out_dir"
set +e
export AI={shlex.quote(ai_cmd)}
export OUT_DIR="$out_dir"
export JSON_FILE="$json_file"
prompt="$(bash {shlex.quote(str(prompt_script))})"
eval "$AI \\"$prompt\\""
status=$?
set -e
printf '[END] %s EXIT_CODE=%s JSON_FILE=%s OUT_DIR=%s\\n' "$(date -Is)" "$status" "$json_file" "$out_dir"
exit "$status"
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def make_tty_entry_script(path: Path) -> None:
    body = """#!/usr/bin/env bash
set -euo pipefail
runner="${1:?runner path required}"
json_file="${2:?json_file path required}"
out_dir="${3:?out_dir path required}"
log_file="${4:?log_file path required}"
mkdir -p "$(dirname "$log_file")"
cmd=$(printf '%q %q %q' "$runner" "$json_file" "$out_dir")
exec script -qefc "$cmd" "$log_file"
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


class Manager:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.run_id = args.run_id
        self.run_base = f"{args.session_prefix}_{self.run_id}"
        self.run_dir = args.tmux_runs_dir / self.run_base
        self.manager_log = self.run_dir / "manager.log"
        self.manifest = self.run_dir / "manifest.tsv"
        self.attempts_tsv = self.run_dir / "attempts.tsv"
        self.state_json = self.run_dir / "state.json"
        self.runner_script = self.run_dir / "runner.sh"
        self.tty_entry_script = self.run_dir / "tty_entry.sh"
        self.latest_meta = args.tmux_runs_dir / "ququ2023_watch_latest.json"

        self.run_dir.mkdir(parents=True, exist_ok=True)
        make_runner_script(self.runner_script, args.workdir, args.prompt_script, args.ai_cmd, args.dry_run)
        make_tty_entry_script(self.tty_entry_script)

        all_files = sorted(args.source_dir.glob("*.json"))
        files = all_files[args.skip :]
        self.skipped_processed: list[tuple[Path, Path]] = []
        if args.only_missing:
            filtered: list[Path] = []
            for p in files:
                out_dir = determine_out_dir(args.source_dir, p)
                if out_dir_has_results(out_dir):
                    self.skipped_processed.append((p, out_dir))
                    continue
                filtered.append(p)
            files = filtered
        if args.max_files > 0:
            files = files[: args.max_files]
        self.jobs = [
            Job(index=i, json_file=str(path), out_dir=str(determine_out_dir(args.source_dir, path)))
            for i, path in enumerate(files, start=1)
        ]
        self.active: dict[str, Job] = {}
        self.last_report_at = 0.0

        self.manifest.write_text("index\tjson_file\tout_dir\n", encoding="utf-8")
        with self.manifest.open("a", encoding="utf-8") as fh:
            for job in self.jobs:
                fh.write(f"{job.index}\t{job.json_file}\t{job.out_dir}\n")

        self.attempts_tsv.write_text(
            "index\tattempt\tsession\tlog_file\tstarted_at\tjson_file\tout_dir\n",
            encoding="utf-8",
        )
        self.write_meta()
        self.write_state()

    def write_meta(self) -> None:
        payload = {
            "run_id": self.run_id,
            "run_base": self.run_base,
            "run_dir": str(self.run_dir),
            "manager_log": str(self.manager_log),
            "manifest": str(self.manifest),
            "attempts_tsv": str(self.attempts_tsv),
            "state_json": str(self.state_json),
            "runner": str(self.runner_script),
            "tty_entry": str(self.tty_entry_script),
            "source_dir": str(self.args.source_dir),
            "workdir": str(self.args.workdir),
            "prompt_script": str(self.args.prompt_script),
            "ai_cmd": self.args.ai_cmd,
            "only_missing": self.args.only_missing,
            "skipped_processed_count": len(self.skipped_processed),
            "result_rule": "prefer existing same-stem dir, else existing *_processed dir, else create same-stem dir",
        }
        self.latest_meta.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        with self.manager_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def write_state(self) -> None:
        summary = {
            "total": len(self.jobs),
            "skipped_processed": len(self.skipped_processed),
            "pending": sum(1 for job in self.jobs if job.state == "pending"),
            "running": sum(1 for job in self.jobs if job.state == "running"),
            "success": sum(1 for job in self.jobs if job.state == "success"),
            "failed": sum(1 for job in self.jobs if job.state == "failed"),
        }
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "run_id": self.run_id,
            "run_base": self.run_base,
            "summary": summary,
            "jobs": [asdict(job) for job in self.jobs],
        }
        self.state_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def pending_jobs(self) -> list[Job]:
        return [job for job in self.jobs if job.state == "pending"]

    def launch_job(self, job: Job) -> None:
        job.attempts += 1
        job.retries = max(0, job.attempts - 1)
        job.state = "running"
        job.exit_code = None
        job.finished_at = None
        job.started_at = time.time()
        job.session_name = f"{self.run_base}_{job.index:03d}_r{job.attempts}"
        job.log_file = str(self.run_dir / f"{job.index:03d}.attempt{job.attempts}.log")
        job.last_reason = f"launch attempt {job.attempts}"

        timeout_cmd = (
            f"timeout --signal=TERM --kill-after={self.args.kill_after_seconds}s "
            f"{self.args.timeout_minutes}m "
            f"{shlex.quote(str(self.tty_entry_script))} "
            f"{shlex.quote(str(self.runner_script))} "
            f"{shlex.quote(job.json_file)} "
            f"{shlex.quote(job.out_dir)} "
            f"{shlex.quote(job.log_file)}"
        )
        tmux_cmd = f"bash -lc {shlex.quote(timeout_cmd)}"
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", job.session_name, tmux_cmd],
            check=True,
        )
        self.active[job.session_name] = job
        with self.attempts_tsv.open("a", encoding="utf-8") as fh:
            fh.write(
                f"{job.index}\t{job.attempts}\t{job.session_name}\t{job.log_file}\t"
                f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{job.json_file}\t{job.out_dir}\n"
            )
        self.log(
            f"launched session={job.session_name} index={job.index} attempt={job.attempts} "
            f"json={job.json_file} out_dir={job.out_dir}"
        )
        self.write_state()

    def mark_success(self, job: Job, reason: str, exit_code: int | None) -> None:
        if job.session_name:
            self.active.pop(job.session_name, None)
        job.state = "success"
        job.finished_at = time.time()
        job.exit_code = exit_code
        job.last_reason = reason
        self.log(
            f"success index={job.index} attempt={job.attempts} exit_code={exit_code} json={job.json_file} reason={reason}"
        )
        self.write_state()

    def mark_retry(self, job: Job, reason: str, exit_code: int | None = None) -> None:
        old_session = job.session_name
        if old_session:
            self.active.pop(old_session, None)
        job.finished_at = time.time()
        job.exit_code = exit_code
        if job.attempts >= self.args.retry_limit:
            job.state = "failed"
            job.last_reason = f"{reason}; retry limit reached"
            self.log(
                f"failed index={job.index} attempt={job.attempts} exit_code={exit_code} json={job.json_file} reason={job.last_reason}"
            )
        else:
            job.state = "pending"
            job.last_reason = reason
            self.log(
                f"retry index={job.index} next_attempt={job.attempts + 1} last_exit_code={exit_code} json={job.json_file} reason={reason}"
            )
        self.write_state()

    def active_report_line(self, job: Job, now: float) -> str:
        age = (now - job.started_at) if job.started_at else 0.0
        log_age = log_age_seconds(Path(job.log_file)) if job.log_file else None
        panes = list_panes(job.session_name) if job.session_name and session_exists(job.session_name) else []
        pane_state = ",".join(
            f"{pane['current_command'] or '?'}:dead={pane['dead']}" for pane in panes
        ) or "missing"
        log_age_text = "na" if log_age is None else f"{log_age / 60:.1f}m"
        return (
            f"active index={job.index} attempt={job.attempts} session={job.session_name} "
            f"age={age / 60:.1f}m log_age={log_age_text} panes={pane_state}"
        )

    def report(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_report_at < self.args.report_interval_seconds:
            return
        self.last_report_at = now
        pending = sum(1 for job in self.jobs if job.state == "pending")
        running = sum(1 for job in self.jobs if job.state == "running")
        success = sum(1 for job in self.jobs if job.state == "success")
        failed = sum(1 for job in self.jobs if job.state == "failed")
        self.log(
            f"report total={len(self.jobs)} pending={pending} running={running} success={success} failed={failed}"
        )
        for job in list(self.active.values()):
            self.log(self.active_report_line(job, now))

    def handle_completed_or_abnormal(self, job: Job) -> None:
        assert job.session_name is not None
        exists = session_exists(job.session_name)
        log_path = Path(job.log_file) if job.log_file else None

        if not exists:
            exit_code = parse_exit_code(log_path) if log_path else None
            if exit_code == 0 and out_dir_has_results(Path(job.out_dir)):
                self.mark_success(job, "session exited normally with output files", exit_code)
            elif exit_code == 0:
                self.mark_retry(job, "session exited 0 but output dir missing/empty", exit_code)
            else:
                self.mark_retry(job, "session disappeared or non-zero exit", exit_code)
            return

        panes = list_panes(job.session_name)
        if not panes:
            kill_session(job.session_name)
            self.mark_retry(job, "session has no panes", None)
            return

        if any(pane["dead"] == "1" for pane in panes):
            kill_session(job.session_name)
            self.mark_retry(job, "pane_dead=1", None)
            return

        if job.started_at is not None:
            elapsed = time.time() - job.started_at
            hard_limit = self.args.timeout_minutes * 60 + self.args.overrun_grace_seconds
            if elapsed > hard_limit:
                kill_session(job.session_name)
                self.mark_retry(job, f"elapsed>{hard_limit}s", None)
                return

    def refill_slots(self) -> None:
        while len(self.active) < self.args.max_concurrent:
            pending = self.pending_jobs()
            if not pending:
                return
            self.launch_job(pending[0])
            time.sleep(1)

    def run(self) -> int:
        if not self.jobs:
            self.log(f"no json files found in {self.args.source_dir}")
            return 1

        self.log(
            "start "
            f"run_base={self.run_base} total={len(self.jobs)} skip={self.args.skip} only_missing={self.args.only_missing} "
            f"skipped_processed={len(self.skipped_processed)} "
            f"max_concurrent={self.args.max_concurrent} timeout_minutes={self.args.timeout_minutes} "
            f"retry_limit={self.args.retry_limit} report_interval_seconds={self.args.report_interval_seconds} "
            f"dry_run={self.args.dry_run}"
        )

        self.refill_slots()
        self.report(force=True)

        while True:
            for job in list(self.active.values()):
                self.handle_completed_or_abnormal(job)
            self.refill_slots()
            self.report(force=False)

            if all(job.state in {"success", "failed"} for job in self.jobs):
                break
            time.sleep(self.args.poll_interval_seconds)

        self.report(force=True)
        failed = sum(1 for job in self.jobs if job.state == "failed")
        success = sum(1 for job in self.jobs if job.state == "success")
        self.log(f"done success={success} failed={failed} total={len(self.jobs)} run_dir={self.run_dir}")
        return 0 if failed == 0 else 2


def main() -> int:
    args = parse_args()
    if args.skip < 0:
        print("--skip must be >= 0", file=sys.stderr)
        return 2
    if args.max_concurrent <= 0:
        print("--max-concurrent must be > 0", file=sys.stderr)
        return 2
    if args.retry_limit <= 0:
        print("--retry-limit must be > 0", file=sys.stderr)
        return 2
    if args.report_interval_seconds <= 0 or args.poll_interval_seconds <= 0:
        print("--report-interval-seconds and --poll-interval-seconds must be > 0", file=sys.stderr)
        return 2
    manager = Manager(args)
    return manager.run()


if __name__ == "__main__":
    raise SystemExit(main())
