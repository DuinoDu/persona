#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "data/03_transcripts/formal_output.schema.json"
DEFAULT_TRANSCRIPTS_ROOT = ROOT / "data/03_transcripts"
DEFAULT_OUTPUT_ROOT = ROOT / "data/04_check_v1"


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def short_year_label(name: str) -> str:
    m = re.search(r"(20\d{2})", name)
    return m.group(1) if m else name


def normalize_path(path_items: Any) -> str:
    if not path_items:
        return "$"
    parts = []
    for item in path_items:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if parts:
                parts.append(".")
            parts.append(str(item))
    return "$." + "".join(parts).lstrip(".")


def compact_keys(obj: Any) -> list[str]:
    if isinstance(obj, dict):
        return sorted(obj.keys())
    if isinstance(obj, list):
        return ["__list__"]
    return [type(obj).__name__]


def top_level_shape(obj: Any) -> str:
    return "|".join(compact_keys(obj))


def is_schema_applicable(obj: Any) -> bool:
    return isinstance(obj, dict) and "meta" in obj and "sentences" in obj


def validate_schema(obj: dict[str, Any], validator: Draft202012Validator) -> list[Issue]:
    issues: list[Issue] = []
    errors = sorted(validator.iter_errors(obj), key=lambda e: (list(e.path), e.message))
    for err in errors:
        issues.append(
            Issue(
                severity="error",
                code="schema_validation_error",
                path=normalize_path(err.path),
                message=err.message,
            )
        )
    return issues


def validate_semantics(obj: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    meta = obj.get("meta")
    sentences = obj.get("sentences")
    if not isinstance(meta, dict) or not isinstance(sentences, list):
        return issues

    start = meta.get("start")
    end = meta.get("end")
    sentence_count = meta.get("sentence_count")

    if isinstance(sentence_count, int) and sentence_count != len(sentences):
        issues.append(
            Issue(
                severity="error",
                code="sentence_count_mismatch",
                path="$.meta.sentence_count",
                message=f"meta.sentence_count={sentence_count} but len(sentences)={len(sentences)}",
            )
        )

    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and start > end:
        issues.append(
            Issue(
                severity="error",
                code="section_time_reversed",
                path="$.meta",
                message=f"section start {start} > end {end}",
            )
        )

    for idx, sentence in enumerate(sentences):
        if not isinstance(sentence, dict):
            issues.append(
                Issue(
                    severity="error",
                    code="sentence_not_object",
                    path=f"$.sentences[{idx}]",
                    message=f"sentence at index {idx} is not an object",
                )
            )
            continue

        s_start = sentence.get("start")
        s_end = sentence.get("end")
        text = sentence.get("text")
        if isinstance(s_start, (int, float)) and isinstance(s_end, (int, float)) and s_start > s_end:
            issues.append(
                Issue(
                    severity="error",
                    code="sentence_time_reversed",
                    path=f"$.sentences[{idx}]",
                    message=f"sentence start {s_start} > end {s_end}",
                )
            )
        if (
            isinstance(start, (int, float))
            and isinstance(end, (int, float))
            and isinstance(s_start, (int, float))
            and isinstance(s_end, (int, float))
            and (s_start < start - 1e-6 or s_end > end + 1e-6)
        ):
            issues.append(
                Issue(
                    severity="warning",
                    code="sentence_outside_section",
                    path=f"$.sentences[{idx}]",
                    message=f"sentence [{s_start}, {s_end}] outside section [{start}, {end}]",
                )
            )
        if isinstance(text, str) and not text.strip():
            issues.append(
                Issue(
                    severity="warning",
                    code="empty_sentence_text",
                    path=f"$.sentences[{idx}].text",
                    message="sentence text is empty after strip()",
                )
            )
    return issues


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total_files": len(records),
        "json_load_fail": 0,
        "schema_applicable": 0,
        "schema_valid": 0,
        "schema_invalid": 0,
        "non_applicable": 0,
        "qc_status_counts": Counter(),
        "top_level_shapes": Counter(),
        "issue_code_counts": Counter(),
        "severity_counts": Counter(),
        "invalid_examples": [],
    }

    for record in records:
        summary["qc_status_counts"][record["qc_status"]] += 1
        summary["top_level_shapes"][record["top_level_shape"]] += 1
        if record["parse_status"] != "ok":
            summary["json_load_fail"] += 1
        if record["schema_applicable"]:
            summary["schema_applicable"] += 1
            if record["schema_valid"]:
                summary["schema_valid"] += 1
            else:
                summary["schema_invalid"] += 1
        else:
            summary["non_applicable"] += 1

        for issue in record["issues"]:
            summary["issue_code_counts"][issue["code"]] += 1
            summary["severity_counts"][issue["severity"]] += 1

        if record["qc_status"] == "fail" and len(summary["invalid_examples"]) < 50:
            summary["invalid_examples"].append(
                {
                    "path": record["path"],
                    "schema_applicable": record["schema_applicable"],
                    "first_issues": record["issues"][:5],
                }
            )

    for key in ("qc_status_counts", "top_level_shapes", "issue_code_counts", "severity_counts"):
        summary[key] = dict(summary[key].most_common())
    return summary


def build_record(path: Path, base_root: Path, validator: Draft202012Validator) -> dict[str, Any]:
    rel = path.relative_to(base_root)
    relative_path = rel.as_posix()
    year = rel.parts[0] if rel.parts else "unknown"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": relative_path,
            "year": year,
            "parse_status": "load_error",
            "top_level_shape": "__parse_error__",
            "schema_applicable": False,
            "schema_valid": False,
            "qc_status": "fail",
            "issues": [
                Issue(
                    severity="error",
                    code="json_load_error",
                    path="$",
                    message=str(exc),
                ).to_dict()
            ],
        }

    issues: list[Issue] = []
    applicable = is_schema_applicable(obj)
    schema_valid = False
    meta = obj.get("meta") if isinstance(obj, dict) else None

    if applicable:
        issues.extend(validate_schema(obj, validator))
        issues.extend(validate_semantics(obj))
        schema_valid = not any(issue.code == "schema_validation_error" for issue in issues)

    has_errors = any(issue.severity == "error" for issue in issues)
    has_warnings = any(issue.severity == "warning" for issue in issues)

    if applicable:
        qc_status = "fail" if has_errors else ("warn" if has_warnings else "pass")
    else:
        qc_status = "skip"

    record = {
        "path": relative_path,
        "year": year,
        "parse_status": "ok",
        "top_level_shape": top_level_shape(obj),
        "schema_applicable": applicable,
        "schema_valid": schema_valid,
        "qc_status": qc_status,
        "issues": [issue.to_dict() for issue in issues],
    }

    if applicable and isinstance(meta, dict):
        record["meta_brief"] = {
            "kind": meta.get("kind"),
            "persona": meta.get("persona"),
            "title": meta.get("title"),
            "sentence_count": meta.get("sentence_count"),
        }

    return record


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_readme(path: Path, combined: dict[str, Any], per_year: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# formal_output QC v1",
        "",
        f"- schema: `{DEFAULT_SCHEMA.relative_to(ROOT).as_posix()}`",
        f"- checked years: {', '.join(sorted(per_year.keys()))}",
        "",
        "## Combined",
        "",
        f"- total_files: {combined['total_files']}",
        f"- schema_applicable: {combined['schema_applicable']}",
        f"- schema_valid: {combined['schema_valid']}",
        f"- schema_invalid: {combined['schema_invalid']}",
        f"- non_applicable: {combined['non_applicable']}",
        f"- json_load_fail: {combined['json_load_fail']}",
        "",
        "## Per year",
        "",
    ]
    for year, summary in sorted(per_year.items()):
        lines.extend(
            [
                f"### {year}",
                f"- total_files: {summary['total_files']}",
                f"- schema_applicable: {summary['schema_applicable']}",
                f"- schema_valid: {summary['schema_valid']}",
                f"- schema_invalid: {summary['schema_invalid']}",
                f"- non_applicable: {summary['non_applicable']}",
                f"- json_load_fail: {summary['json_load_fail']}",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="QC formal transcript outputs against formal_output.schema.json")
    ap.add_argument(
        "--years",
        nargs="+",
        default=["曲曲2025（全）", "曲曲2026"],
        help="Year directories under data/03_transcripts to scan",
    )
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    ap.add_argument("--transcripts-root", default=str(DEFAULT_TRANSCRIPTS_ROOT))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_ROOT))
    args = ap.parse_args()

    schema_path = Path(args.schema)
    transcripts_root = Path(args.transcripts_root)
    out_dir = Path(args.out_dir)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    per_year_summaries: dict[str, dict[str, Any]] = {}
    combined_records: list[dict[str, Any]] = []

    for year in args.years:
        year_root = transcripts_root / year
        records: list[dict[str, Any]] = []
        for path in sorted(year_root.rglob("*.json")):
            records.append(build_record(path, transcripts_root, validator))

        year_label = short_year_label(year)
        summary = summarize_records(records)
        summary["year"] = year
        per_year_summaries[year] = summary
        combined_records.extend(records)

        invalid_records = [record for record in records if record["qc_status"] == "fail"]
        applicable_records = [record for record in records if record["schema_applicable"]]

        write_json(out_dir / f"{year_label}_summary.json", summary)
        write_jsonl(out_dir / f"{year_label}_records.jsonl", records)
        write_jsonl(out_dir / f"{year_label}_formal_records.jsonl", applicable_records)
        write_jsonl(out_dir / f"{year_label}_invalid.jsonl", invalid_records)

    combined_summary = summarize_records(combined_records)
    combined_summary["years"] = args.years
    write_json(out_dir / "combined_summary.json", combined_summary)
    write_readme(out_dir / "README.md", combined_summary, per_year_summaries)

    print(json.dumps(combined_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
