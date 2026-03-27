#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Continuously reconcile a running ququ queue state.json with repaired job overrides."
    )
    parser.add_argument("--state-json", type=Path, required=True)
    parser.add_argument("--repair-state-json", type=Path, required=True)
    parser.add_argument("--repair-log", type=Path, required=True)
    parser.add_argument("--target-json-name", required=True)
    parser.add_argument("--interval-seconds", type=int, default=5)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def log_line(log_path: Path, message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def repair_ready(repair_state_json: Path) -> tuple[bool, dict | None]:
    if not repair_state_json.exists():
        return False, None
    try:
        payload = load_json(repair_state_json)
    except Exception:
        return False, None
    summary = payload.get("summary", {})
    if summary.get("success", 0) < 1:
        return False, payload
    return True, payload


def recompute_summary(jobs: list[dict]) -> dict[str, int]:
    counts = {
        "total": len(jobs),
        "skipped_processed": 0,
        "pending": 0,
        "running": 0,
        "success": 0,
        "failed": 0,
        "repaired": 0,
    }
    for job in jobs:
        state = job.get("state")
        if state in counts:
            counts[state] += 1
    return counts


def maybe_patch_state(
    state_json: Path,
    repair_state_json: Path,
    repair_log: Path,
    target_json_name: str,
) -> bool:
    ready, repair_payload = repair_ready(repair_state_json)
    if not ready or repair_payload is None:
        return False

    try:
        state_payload = load_json(state_json)
    except Exception as exc:
        log_line(repair_log, f"state json not ready: {exc}")
        return False

    jobs = state_payload.get("jobs", [])
    patched = False
    for job in jobs:
        json_file = Path(job.get("json_file", "")).name
        if json_file != target_json_name:
            continue
        if job.get("state") == "repaired":
            return True
        old_state = job.get("state")
        job["patched_from_state"] = old_state
        job["state"] = "repaired"
        job["exit_code"] = 0
        job["last_reason"] = (
            "repaired by standalone rerun "
            + str(repair_payload.get("run_base", repair_payload.get("run_id", "unknown")))
        )
        job["repaired_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        patched = True
        break

    if not patched:
        return False

    state_payload["summary"] = recompute_summary(jobs)
    state_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state_payload["repaired_jobs"] = [
        {
            "json_name": target_json_name,
            "repair_run_id": repair_payload.get("run_id"),
            "repair_run_base": repair_payload.get("run_base"),
            "repair_state_json": str(repair_state_json),
        }
    ]
    atomic_write_json(state_json, state_payload)
    log_line(repair_log, f"patched {target_json_name} from failed to repaired")
    return True


def main() -> int:
    args = parse_args()
    args.repair_log.parent.mkdir(parents=True, exist_ok=True)
    log_line(args.repair_log, "reconciler started")

    patched_once = False
    while True:
        if args.state_json.exists():
            try:
                patched_now = maybe_patch_state(
                    args.state_json,
                    args.repair_state_json,
                    args.repair_log,
                    args.target_json_name,
                )
                patched_once = patched_once or patched_now
            except Exception as exc:
                log_line(args.repair_log, f"patch error: {exc}")

            try:
                payload = load_json(args.state_json)
                summary = payload.get("summary", {})
                pending = int(summary.get("pending", 0))
                running = int(summary.get("running", 0))
                if patched_once and pending == 0 and running == 0:
                    log_line(args.repair_log, "main queue finished; reconciler exiting")
                    return 0
            except Exception:
                pass

        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
