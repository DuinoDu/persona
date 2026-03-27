#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / "data/03_transcripts"
QC_ROOT = ROOT / "data/04_check_v1"
SCHEMA_PATH = TRANSCRIPTS_ROOT / "formal_output.schema.json"
YEARS = ["曲曲2025（全）", "曲曲2026"]

HOST_NAME = "曲曲"
GUEST_NAME = "嘉宾"
DEFAULT_NOTE = "qc_safe_fix_v1: 保守修复 schema 字段与句子字段，不改写文本内容。"

SAFE_SCHEMA_MESSAGES = {
    "'speaker_name' is a required property",
    "Additional properties are not allowed ('speaker_raw' was unexpected)",
    "Additional properties are not allowed ('call_index', 'type' were unexpected)",
    "'notes' is a required property",
    "'index' is a required property",
    "'kind' is a required property",
    "'raw_segment_count' is a required property",
    "'sentence_count' is a required property",
    "'speaker_ids' is a required property",
    "'speaker_names' is a required property",
    "'start_ts' is a required property",
    "'end_ts' is a required property",
    "'title' is a required property",
    "['host', 'guest'] was expected",
    "['host'] was expected",
    "[] should be non-empty",
    "'host' is a required property",
}


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def parse_filename(filename: str) -> dict[str, Any] | None:
    stem = filename[:-5] if filename.endswith(".json") else filename
    m = re.match(r"^(\d+?)_(.+)$", stem)
    if not m:
        return None
    index = int(m.group(1))
    rest = m.group(2)
    if stem == "00_开场" or rest == "开场":
        return {"index": index, "kind": "opening", "persona": "开场", "title": stem}
    if rest.endswith("_连麦"):
        return {"index": index, "kind": "call", "persona": rest[: -len("_连麦")], "title": stem}
    if rest.endswith("_评论"):
        return {"index": index, "kind": "comment", "persona": rest[: -len("_评论")], "title": stem}
    return None


def expected_speakers(kind: str) -> tuple[list[str], dict[str, str]]:
    if kind == "call":
        return ["host", "guest"], {"host": HOST_NAME, "guest": GUEST_NAME}
    return ["host"], {"host": HOST_NAME}


def load_schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def rank_candidate(path: Path) -> tuple[int, int, str]:
    rel = path.as_posix()
    is_backup = 1 if "backup" in rel else 0
    is_processed = 1 if "_processed" in rel else 0
    return (is_backup, is_processed, rel)


def build_valid_index(validator: Draft202012Validator) -> dict[tuple[str, str, str], Path]:
    candidates: dict[tuple[str, str, str], list[Path]] = defaultdict(list)
    for year in YEARS:
        year_root = TRANSCRIPTS_ROOT / year
        for path in year_root.rglob("*.json"):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not (isinstance(obj, dict) and set(obj.keys()) == {"meta", "sentences"}):
                continue
            if any(validator.iter_errors(obj)):
                continue
            meta = obj.get("meta", {})
            source_file = meta.get("source_file")
            if not isinstance(source_file, str):
                continue
            key = (year, path.name, source_file)
            candidates[key].append(path)
    chosen: dict[tuple[str, str, str], Path] = {}
    for key, paths in candidates.items():
        chosen[key] = sorted(paths, key=rank_candidate)[0]
    return chosen


def load_invalid_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for year in ("2025", "2026"):
        path = QC_ROOT / f"{year}_invalid.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def record_is_safe(record: dict[str, Any]) -> bool:
    if record.get("parse_status") != "ok":
        return False
    rel = str(record.get("path", ""))
    if "backup" in rel:
        return False
    issues = record.get("issues", [])
    for issue in issues:
        code = issue.get("code")
        if code == "schema_validation_error":
            msg = issue.get("message", "")
            if msg in SAFE_SCHEMA_MESSAGES:
                continue
            if "does not match '^\\\\d{2}:\\\\d{2}:\\\\d{2}\\\\.\\\\d{2}$'" in msg:
                continue
            return False
        if code in {"json_load_error", "section_time_reversed", "sentence_count_mismatch"}:
            return False
    return True


def normalize_sentences(sentences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for sentence in sentences:
        if not isinstance(sentence, dict):
            raise ValueError("sentence is not object")
        item = dict(sentence)
        item.pop("speaker_raw", None)
        speaker_id = item.get("speaker_id")
        if "speaker_name" not in item and speaker_id == "host":
            item["speaker_name"] = HOST_NAME
        elif "speaker_name" not in item and speaker_id == "guest":
            item["speaker_name"] = GUEST_NAME
        normalized.append(item)
    return normalized


def normalize_meta(
    path: Path,
    meta: dict[str, Any],
    sentences: list[dict[str, Any]],
    counterpart_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(meta)
    result.pop("type", None)
    result.pop("call_index", None)

    inferred = parse_filename(path.name) or {}
    kind = result.get("kind") or (counterpart_meta or {}).get("kind") or inferred.get("kind")
    if kind not in {"opening", "call", "comment"}:
        raise ValueError(f"cannot determine kind for {path}")

    expected_ids, expected_names = expected_speakers(kind)

    if counterpart_meta:
        for key in [
            "index",
            "kind",
            "title",
            "start_ts",
            "end_ts",
            "raw_segment_count",
            "speaker_ids",
            "speaker_names",
            "notes",
        ]:
            if key not in result and key in counterpart_meta:
                result[key] = counterpart_meta[key]

    if "index" not in result:
        if "index" in inferred:
            result["index"] = inferred["index"]
        else:
            raise ValueError(f"missing index without safe inference: {path}")
    result["kind"] = kind

    if "persona" not in result or result.get("persona") in (None, ""):
        if counterpart_meta and counterpart_meta.get("persona"):
            result["persona"] = counterpart_meta["persona"]
        elif inferred.get("persona") is not None:
            result["persona"] = inferred["persona"]
        else:
            result["persona"] = ""

    if "title" not in result:
        result["title"] = inferred.get("title") or path.stem

    if "start_ts" not in result:
        result["start_ts"] = ts(float(result["start"]))
    else:
        result["start_ts"] = ts(float(result["start"]))
    if "end_ts" not in result:
        result["end_ts"] = ts(float(result["end"]))
    else:
        result["end_ts"] = ts(float(result["end"]))

    if "raw_segment_count" not in result:
        if counterpart_meta and "raw_segment_count" in counterpart_meta:
            result["raw_segment_count"] = counterpart_meta["raw_segment_count"]
        else:
            raise ValueError(f"missing raw_segment_count without counterpart: {path}")

    result["sentence_count"] = len(sentences)

    existing_ids = result.get("speaker_ids")
    if isinstance(existing_ids, list) and set(existing_ids) == set(expected_ids):
        result["speaker_ids"] = expected_ids
    elif not existing_ids:
        if kind == "call":
            sentence_ids = {s.get("speaker_id") for s in sentences}
            if set(expected_ids).issubset(sentence_ids) or counterpart_meta is not None:
                result["speaker_ids"] = expected_ids
            else:
                raise ValueError(f"call speaker_ids not safely inferable: {path}")
        else:
            result["speaker_ids"] = expected_ids
    else:
        raise ValueError(f"speaker_ids not safely normalizable: {path}")

    result["speaker_names"] = expected_names
    if "notes" not in result or not isinstance(result.get("notes"), str) or not result.get("notes"):
        result["notes"] = (counterpart_meta or {}).get("notes") or DEFAULT_NOTE

    return result


def fix_one_file(
    path: Path,
    validator: Draft202012Validator,
    valid_index: dict[tuple[str, str, str], Path],
    backup_root: Path,
) -> dict[str, Any] | None:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(obj, dict) and "meta" in obj and "sentences" in obj):
        return None

    meta = obj["meta"]
    sentences = obj["sentences"]
    if not isinstance(meta, dict) or not isinstance(sentences, list):
        return None

    rel = path.relative_to(TRANSCRIPTS_ROOT)
    year = rel.parts[0]
    source_file = meta.get("source_file")
    counterpart_meta = None
    counterpart = None
    if isinstance(source_file, str):
        counterpart = valid_index.get((year, path.name, source_file))
        if counterpart and counterpart != path:
            counterpart_obj = json.loads(counterpart.read_text(encoding="utf-8"))
            counterpart_meta = counterpart_obj["meta"]

    fixed_sentences = normalize_sentences(sentences)
    fixed_meta = normalize_meta(path, meta, fixed_sentences, counterpart_meta)
    fixed_obj = {"meta": fixed_meta, "sentences": fixed_sentences}

    errors = list(validator.iter_errors(fixed_obj))
    if errors:
        raise ValueError("; ".join(err.message for err in errors[:5]))

    backup_path = backup_root / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    path.write_text(json.dumps(fixed_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "path": rel.as_posix(),
        "backup_path": backup_path.relative_to(ROOT).as_posix(),
        "counterpart": str(counterpart.relative_to(ROOT)) if counterpart_meta and counterpart else None,
    }


def main() -> None:
    validator = load_schema_validator()
    valid_index = build_valid_index(validator)
    records = load_invalid_records()

    backup_root = QC_ROOT / "safe_fix_v1_backup"
    log_path = QC_ROOT / "safe_fix_v1_log.jsonl"
    skipped_path = QC_ROOT / "safe_fix_v1_skipped.jsonl"

    fixed_logs: list[dict[str, Any]] = []
    skipped_logs: list[dict[str, Any]] = []

    for record in records:
        rel = record["path"]
        path = TRANSCRIPTS_ROOT / rel
        if not record_is_safe(record):
            skipped_logs.append({"path": rel, "reason": "unsafe_issue_pattern"})
            continue
        try:
            result = fix_one_file(path, validator, valid_index, backup_root)
        except Exception as exc:
            skipped_logs.append({"path": rel, "reason": str(exc)})
            continue
        if result:
            fixed_logs.append(result)
        else:
            skipped_logs.append({"path": rel, "reason": "not_fixable"})

    with log_path.open("w", encoding="utf-8") as fh:
        for row in fixed_logs:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    with skipped_path.open("w", encoding="utf-8") as fh:
        for row in skipped_logs:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "fixed_count": len(fixed_logs),
        "skipped_count": len(skipped_logs),
        "log_file": str(log_path.relative_to(ROOT)),
        "skipped_file": str(skipped_path.relative_to(ROOT)),
        "backup_root": str(backup_root.relative_to(ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
