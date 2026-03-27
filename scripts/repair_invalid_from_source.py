#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / "data/03_transcripts"
QC_ROOT = ROOT / "data/04_check_v1"
SCHEMA_PATH = TRANSCRIPTS_ROOT / "formal_output.schema.json"
INVALID_LIST = ROOT / "invalid.txt"
BACKUP_ROOT = QC_ROOT / "repair_invalid_from_source_backup"
LOG_PATH = QC_ROOT / "repair_invalid_from_source_log.jsonl"
SKIP_PATH = QC_ROOT / "repair_invalid_from_source_skipped.jsonl"

HOST_NAME = "曲曲"
GUEST_NAME = "嘉宾"


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def try_read_json(path: Path) -> Any | None:
    try:
        return read_json(path)
    except Exception:
        return None


def parse_title(filename: str) -> dict[str, Any]:
    stem = filename[:-5] if filename.endswith(".json") else filename
    m = re.match(r"^(\d+?)_(.+)$", stem)
    if not m:
        return {"index": 0, "kind": "comment", "persona": stem, "title": stem}
    index = int(m.group(1))
    rest = m.group(2)
    if rest == "开场":
        return {"index": index, "kind": "opening", "persona": "开场", "title": stem}
    if rest.endswith("_连麦"):
        return {"index": index, "kind": "call", "persona": rest[: -len("_连麦")], "title": stem}
    if rest.endswith("_评论"):
        return {"index": index, "kind": "comment", "persona": rest[: -len("_评论")], "title": stem}
    return {"index": index, "kind": "comment", "persona": rest, "title": stem}


def expected_speakers(kind: str) -> tuple[list[str], dict[str, str]]:
    if kind == "call":
        return ["host", "guest"], {"host": HOST_NAME, "guest": GUEST_NAME}
    return ["host"], {"host": HOST_NAME}


def list_invalid_paths() -> list[Path]:
    lines = [x.strip() for x in INVALID_LIST.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [TRANSCRIPTS_ROOT / x for x in lines]


def find_manifest_entry(target_path: Path) -> dict[str, Any] | None:
    for ancestor in [target_path.parent, *target_path.parents]:
        if ancestor == TRANSCRIPTS_ROOT.parent:
            break
        for name in ("_section_manifest.raw.json", "_section_manifest.json"):
            manifest_path = ancestor / name
            if not manifest_path.exists():
                continue
            obj = try_read_json(manifest_path)
            if not isinstance(obj, dict):
                continue
            for entry in obj.get("sections", []):
                if isinstance(entry, dict) and entry.get("file") == target_path.name:
                    merged = dict(entry)
                    for key in ("source_file", "source_dir"):
                        if key in obj and key not in merged:
                            merged[key] = obj[key]
                    return merged
    return None


def find_adjacent_meta(target_path: Path) -> dict[str, Any] | None:
    title = parse_title(target_path.name)
    idx = title["index"]
    siblings = []
    for p in sorted(target_path.parent.glob("*.json")):
        if p == target_path:
            continue
        obj = try_read_json(p)
        if isinstance(obj, dict) and "meta" in obj and isinstance(obj["meta"], dict):
            siblings.append((parse_title(p.name)["index"], p, obj["meta"]))
    prev_meta = None
    next_meta = None
    for s_idx, _, meta in siblings:
        if s_idx < idx and (prev_meta is None or s_idx > prev_meta[0]):
            prev_meta = (s_idx, meta)
        if s_idx > idx and (next_meta is None or s_idx < next_meta[0]):
            next_meta = (s_idx, meta)
    if prev_meta or next_meta:
        meta: dict[str, Any] = {}
        if prev_meta:
            meta["start"] = prev_meta[1].get("end")
            meta["source_file"] = prev_meta[1].get("source_file")
        if next_meta:
            meta["end"] = next_meta[1].get("start")
            meta.setdefault("source_file", next_meta[1].get("source_file"))
        meta.update(title)
        return meta
    return None


def extract_meta(target_path: Path) -> dict[str, Any]:
    title_info = parse_title(target_path.name)
    obj = try_read_json(target_path)
    obj_meta = dict(obj["meta"]) if isinstance(obj, dict) and isinstance(obj.get("meta"), dict) else {}
    manifest_entry = find_manifest_entry(target_path)
    if manifest_entry:
        meta = dict(manifest_entry)
        if "source_file" not in meta and obj_meta.get("source_file"):
            meta["source_file"] = obj_meta["source_file"]
        meta.update({k: meta.get(k) or v for k, v in title_info.items()})
        return meta

    if isinstance(obj, dict) and "meta" in obj and isinstance(obj["meta"], dict):
        meta = dict(obj["meta"])
        meta.update({k: meta.get(k) or v for k, v in title_info.items()})
        return meta
    adjacent = find_adjacent_meta(target_path)
    if adjacent:
        return adjacent
    raise ValueError(f"cannot infer meta for {target_path}")


def resolve_source_path(target_path: Path, source_file: str) -> Path:
    for ancestor in [target_path.parent, *target_path.parents]:
        candidate = ancestor / source_file
        if candidate.exists():
            return candidate
        if ancestor == TRANSCRIPTS_ROOT:
            break
    year_root = TRANSCRIPTS_ROOT / target_path.relative_to(TRANSCRIPTS_ROOT).parts[0]
    matches = sorted([p for p in year_root.rglob(source_file) if p.exists()], key=lambda p: (("backup" in str(p)), len(str(p))))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"source file not found for {target_path}: {source_file}")


def load_source_units(source_path: Path) -> tuple[str, list[dict[str, Any]]]:
    obj = read_json(source_path)
    if isinstance(obj, dict) and "segments" in obj and isinstance(obj["segments"], list):
        units = []
        for seg in obj["segments"]:
            if not isinstance(seg, dict):
                continue
            units.append(
                {
                    "start": float(seg["start"]),
                    "end": float(seg["end"]),
                    "speaker": seg.get("speaker", "UNKNOWN"),
                    "text": seg.get("text", ""),
                    "source_type": "raw",
                }
            )
        return "raw", units
    if isinstance(obj, dict) and "sentences" in obj and isinstance(obj["sentences"], list):
        units = []
        for sent in obj["sentences"]:
            if not isinstance(sent, dict):
                continue
            units.append(
                {
                    "start": float(sent["start"]),
                    "end": float(sent["end"]),
                    "speaker_id": sent.get("speaker_id", "host"),
                    "speaker_name": sent.get("speaker_name", HOST_NAME),
                    "text": sent.get("text", ""),
                    "source_type": "formal",
                }
            )
        return "formal", units
    raise ValueError(f"unsupported source structure: {source_path}")


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def section_distance(start0: float, end0: float, start1: float, end1: float) -> float:
    if end0 < start1:
        return start1 - end0
    if end1 < start0:
        return start0 - end1
    return 0.0


def gather_reference_sections(
    year_root: Path,
    source_file_name: str,
    target_path: Path,
    target_start: float,
    target_end: float,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for path in year_root.rglob("*.json"):
        if path == target_path:
            continue
        obj = try_read_json(path)
        if not (isinstance(obj, dict) and "meta" in obj and "sentences" in obj):
            continue
        meta = obj["meta"]
        if isinstance(meta, dict) and meta.get("source_file") == source_file_name:
            refs.append(
                {
                    "path": path,
                    "obj": obj,
                    "meta": meta,
                    "distance": section_distance(
                        float(meta.get("start", 0)),
                        float(meta.get("end", 0)),
                        target_start,
                        target_end,
                    ),
                }
            )
    refs.sort(key=lambda item: (item["distance"], str(item["path"])))
    return refs


def infer_host_speakers_from_refs(source_units: list[dict[str, Any]], refs: list[dict[str, Any]]) -> set[str]:
    reliable_refs = [item for item in refs if item["meta"].get("kind") in {"opening", "comment"}]
    if reliable_refs:
        refs = reliable_refs[:6]
    else:
        refs = refs[:6]

    host_overlap: Counter = Counter()
    for item in refs:
        obj = item["obj"]
        weight = 1.0 / (1.0 + float(item["distance"]) / 300.0)
        for sent in obj.get("sentences", []):
            if not isinstance(sent, dict) or sent.get("speaker_id") != "host":
                continue
            s0 = float(sent["start"])
            s1 = float(sent["end"])
            for unit in source_units:
                ov = overlap(s0, s1, unit["start"], unit["end"])
                if ov > 0:
                    host_overlap[unit["speaker"]] += ov * weight

    if not host_overlap:
        return set()

    max_host = max(host_overlap.values())
    return {speaker for speaker, value in host_overlap.items() if value >= max(0.8, max_host * 0.2)}


def compute_active_raw_durations(source_units: list[dict[str, Any]], start: float, end: float) -> Counter:
    active: Counter = Counter()
    for unit in source_units:
        ov = overlap(start, end, unit["start"], unit["end"])
        if ov > 0:
            active[unit["speaker"]] += ov
    return active


def compute_current_role_overlap(current_obj: dict[str, Any] | None, source_units: list[dict[str, Any]]) -> dict[str, Counter]:
    role_overlap: dict[str, Counter] = defaultdict(Counter)
    if not (isinstance(current_obj, dict) and isinstance(current_obj.get("sentences"), list)):
        return role_overlap
    for sent in current_obj.get("sentences", []):
        if not isinstance(sent, dict):
            continue
        role = sent.get("speaker_id")
        if role not in {"host", "guest", "unknown"}:
            continue
        s0 = float(sent["start"])
        s1 = float(sent["end"])
        for unit in source_units:
            ov = overlap(s0, s1, unit["start"], unit["end"])
            if ov > 0:
                role_overlap[role][unit["speaker"]] += ov
    return role_overlap


def infer_call_speaker_sets(
    current_obj: dict[str, Any] | None,
    source_units: list[dict[str, Any]],
    start: float,
    end: float,
    host_ref_speakers: set[str],
) -> tuple[set[str], set[str], Counter]:
    active = compute_active_raw_durations(source_units, start, end)
    role_overlap = compute_current_role_overlap(current_obj, source_units)

    host_speakers = {spk for spk in host_ref_speakers if active.get(spk, 0) > 0}
    if not host_speakers and role_overlap.get("host"):
        top = max(role_overlap["host"].values())
        host_speakers = {
            spk
            for spk, value in role_overlap["host"].items()
            if value >= max(0.8, top * 0.35) and active.get(spk, 0) > 0
        }

    guest_speakers: set[str] = set()
    guest_overlap = role_overlap.get("guest", Counter())
    if guest_overlap:
        ranked_guest = guest_overlap.most_common()
        for top_guest_speaker, top_guest_value in ranked_guest:
            if top_guest_speaker in host_speakers:
                continue
            if top_guest_speaker == "UNKNOWN" and any(
                spk not in host_speakers and spk != "UNKNOWN" for spk in active
            ):
                continue
            if top_guest_value >= 0.8:
                guest_speakers.add(top_guest_speaker)
                break

    if not guest_speakers:
        non_host = [(spk, dur) for spk, dur in active.most_common() if spk not in host_speakers]
        if non_host:
            guest_speakers.add(non_host[0][0])

    if not host_speakers:
        top_guest = next(iter(guest_speakers), None)
        remaining = [(spk, dur) for spk, dur in active.most_common() if spk != top_guest]
        if remaining:
            max_remaining = remaining[0][1]
            host_speakers = {
                spk for spk, dur in remaining if dur >= max(0.8, max_remaining * 0.25)
            }
        elif top_guest is not None:
            host_speakers = {top_guest}
            guest_speakers = set()

    if guest_speakers and len(host_speakers) > 1:
        host_speakers -= guest_speakers

    if not guest_speakers:
        non_host = [(spk, dur) for spk, dur in active.most_common() if spk not in host_speakers]
        if non_host:
            guest_speakers.add(non_host[0][0])

    return host_speakers, guest_speakers, active


def dominant_raw_speaker(source_units: list[dict[str, Any]], start: float, end: float) -> str | None:
    c = Counter()
    for unit in source_units:
        ov = overlap(start, end, unit["start"], unit["end"])
        if ov > 0:
            c[unit["speaker"]] += ov
    if c:
        return c.most_common(1)[0][0]
    nearest = None
    best = None
    for unit in source_units:
        dist = min(abs(unit["start"] - start), abs(unit["end"] - end))
        if best is None or dist < best:
            best = dist
            nearest = unit["speaker"]
    return nearest


def canonical_sentence(role: str, start: float, end: float, text: str) -> dict[str, Any]:
    return {
        "speaker_id": role,
        "speaker_name": HOST_NAME if role == "host" else GUEST_NAME,
        "start": round(float(start), 2),
        "end": round(float(end), 2),
        "text": text.strip(),
    }


def fix_parseable_with_source(
    obj: dict[str, Any],
    source_type: str,
    source_units: list[dict[str, Any]],
    raw_roles: dict[str, str],
    kind: str,
) -> list[dict[str, Any]]:
    fixed: list[dict[str, Any]] = []
    host_speakers = {spk for spk, role in raw_roles.items() if role == "host"}
    for sent in obj.get("sentences", []):
        if not isinstance(sent, dict):
            continue
        text = str(sent.get("text", "")).strip()
        if not text:
            continue
        s0 = float(sent["start"])
        s1 = float(sent["end"])
        role = sent.get("speaker_id")

        if source_type == "raw":
            spk = dominant_raw_speaker(source_units, s0, s1)
            if spk is not None:
                inferred = raw_roles.get(spk)
                if inferred:
                    role = inferred
                elif kind == "call":
                    role = "host" if spk in host_speakers else "guest"
                else:
                    role = "host" if spk in host_speakers else "guest"

        if kind in {"opening", "comment"}:
            if role != "host":
                continue
            role = "host"
        elif role not in {"host", "guest"}:
            role = "guest"

        fixed.append(canonical_sentence(role, s0, s1, text))
    return fixed


def merge_source_units(
    source_type: str,
    source_units: list[dict[str, Any]],
    kind: str,
    host_speakers: set[str],
    guest_speakers: set[str],
    start: float,
    end: float,
) -> list[dict[str, Any]]:
    lo, hi = sorted((start, end))
    if hi - lo < 0.2:
        lo -= 1.0
        hi += 3.0
    selected = [u for u in source_units if u["end"] >= lo and u["start"] <= hi]
    active_durations = compute_active_raw_durations(source_units, lo, hi)
    guest_primary_duration = 0.0
    if guest_speakers:
        guest_primary_duration = max(active_durations.get(spk, 0.0) for spk in guest_speakers)

    units = []
    for u in selected:
        text = str(u.get("text", "")).strip()
        if not text:
            continue
        if source_type == "formal":
            role = u.get("speaker_id", "host")
        else:
            speaker = u["speaker"]
            if kind in {"opening", "comment"}:
                if speaker not in host_speakers:
                    continue
                role = "host"
            else:
                if speaker in host_speakers:
                    role = "host"
                elif guest_speakers:
                    if speaker not in guest_speakers:
                        dur = active_durations.get(speaker, 0.0)
                        if dur < max(1.0, guest_primary_duration * 0.12):
                            continue
                    role = "guest"
                else:
                    role = "guest"
        units.append({"role": role, "start": float(u["start"]), "end": float(u["end"]), "text": text})

    merged: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for u in units:
        if current is None:
            current = dict(u)
            continue
        gap = u["start"] - current["end"]
        if u["role"] == current["role"] and gap <= 0.8 and len(current["text"]) + len(u["text"]) <= 140:
            current["end"] = max(current["end"], u["end"])
            current["text"] += u["text"]
        else:
            merged.append(canonical_sentence(current["role"], current["start"], current["end"], current["text"]))
            current = dict(u)
    if current is not None:
        merged.append(canonical_sentence(current["role"], current["start"], current["end"], current["text"]))
    return merged


def make_meta(base_meta: dict[str, Any], source_file: str, kind: str, persona: str, title: str, sentences: list[dict[str, Any]], raw_count: int) -> dict[str, Any]:
    speaker_ids, speaker_names = expected_speakers(kind)
    if sentences:
        start = min(s["start"] for s in sentences)
        end = max(s["end"] for s in sentences)
    else:
        base_start = float(base_meta.get("start", 0))
        base_end = float(base_meta.get("end", base_start))
        start, end = sorted((base_start, base_end))
    return {
        "source_file": source_file,
        "index": int(base_meta.get("index", parse_title(title).get("index", 0))),
        "kind": kind,
        "persona": persona,
        "title": title,
        "start": round(start, 2),
        "end": round(end, 2),
        "start_ts": ts(start),
        "end_ts": ts(end),
        "raw_segment_count": int(raw_count),
        "speaker_ids": speaker_ids,
        "speaker_names": speaker_names,
        "sentence_count": len(sentences),
        "notes": "repair_invalid_from_source_v1: 按 source_file 对应时间段重建/修复。",
    }


def validate_and_write(target_path: Path, obj: dict[str, Any], validator: Draft202012Validator) -> None:
    errors = list(validator.iter_errors(obj))
    if errors:
        raise ValueError("; ".join(err.message for err in errors[:10]))
    rel = target_path.relative_to(TRANSCRIPTS_ROOT)
    backup_path = BACKUP_ROOT / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_path, backup_path)
    target_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair_one(target_path: Path, validator: Draft202012Validator) -> dict[str, Any]:
    meta = extract_meta(target_path)
    source_file = meta["source_file"]
    kind = meta["kind"]
    persona = meta.get("persona") or parse_title(target_path.name)["persona"]
    title = meta.get("title") or parse_title(target_path.name)["title"]
    source_path = resolve_source_path(target_path, source_file)
    source_type, source_units = load_source_units(source_path)

    current_obj = try_read_json(target_path)
    year_root = TRANSCRIPTS_ROOT / target_path.relative_to(TRANSCRIPTS_ROOT).parts[0]

    host_speakers: set[str] = set()
    guest_speakers: set[str] = set()
    if source_type == "raw":
        ref_infos = gather_reference_sections(
            year_root,
            Path(source_file).name,
            target_path,
            float(meta.get("start", 0)),
            float(meta.get("end", 0)),
        )
        host_speakers = infer_host_speakers_from_refs(source_units, ref_infos)
        if kind == "call":
            host_speakers, guest_speakers, _ = infer_call_speaker_sets(
                current_obj,
                source_units,
                float(meta.get("start", 0)),
                float(meta.get("end", 0)),
                host_speakers,
            )
        elif not host_speakers:
            active = compute_active_raw_durations(source_units, float(meta.get("start", 0)), float(meta.get("end", 0)))
            if active:
                max_active = max(active.values())
                host_speakers = {spk for spk, dur in active.items() if dur >= max(0.8, max_active * 0.25)}

    if source_type == "formal" and isinstance(current_obj, dict) and "meta" in current_obj and "sentences" in current_obj:
        sentences = fix_parseable_with_source(current_obj, source_type, source_units, {}, kind)
    else:
        sentences = merge_source_units(
            source_type,
            source_units,
            kind,
            host_speakers,
            guest_speakers,
            float(meta.get("start", 0)),
            float(meta.get("end", 0)),
        )

    if not sentences and kind == "call":
        raise ValueError("no sentences after repair")

    if sentences:
        repaired_start = min(item["start"] for item in sentences)
        repaired_end = max(item["end"] for item in sentences)
        raw_count = len([u for u in source_units if u["end"] >= repaired_start and u["start"] <= repaired_end])
    else:
        raw_count = 0
    repaired = {
        "meta": make_meta(meta, Path(source_file).name, kind, persona, title, sentences, raw_count),
        "sentences": sentences,
    }
    validate_and_write(target_path, repaired, validator)
    return {
        "path": target_path.relative_to(TRANSCRIPTS_ROOT).as_posix(),
        "source_file": source_path.relative_to(ROOT).as_posix(),
        "sentence_count": len(sentences),
        "kind": kind,
    }


def main() -> None:
    schema = read_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)

    fixed = []
    skipped = []
    for path in list_invalid_paths():
        try:
            result = repair_one(path, validator)
            fixed.append(result)
        except Exception as exc:
            skipped.append({"path": path.relative_to(TRANSCRIPTS_ROOT).as_posix(), "reason": str(exc)})

    with LOG_PATH.open("w", encoding="utf-8") as fh:
        for row in fixed:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with SKIP_PATH.open("w", encoding="utf-8") as fh:
        for row in skipped:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps({"fixed_count": len(fixed), "skipped_count": len(skipped)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
