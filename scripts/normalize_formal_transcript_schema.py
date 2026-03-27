#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("/home/duino/ws/ququ/process_youtube")
TRANSCRIPTS_ROOT = ROOT / "data/03_transcripts/曲曲2025（全）"
SCHEMA_PATH = ROOT / "data/03_transcripts/formal_output.schema.json"
GROUP11 = TRANSCRIPTS_ROOT / "11 - 曲曲現場直播 2025年2月20日 ｜ 曲曲麥肯錫"
GROUP10 = TRANSCRIPTS_ROOT / "10 - 曲曲現場直播 2025年2月14日 ｜ 曲曲麥肯錫"
GROUP10_REDUNDANT = [
    "02_25岁C9硕士事业婚恋_评论.json",
    "06_24岁隐婚遇赌徒富二代_评论.json",
    "12_43岁外资医院主任转型_评论.json",
]


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def title_parts(filename: str) -> tuple[int, str, str, str]:
    stem = filename[:-5] if filename.endswith(".json") else filename
    idx_str, rest = stem.split("_", 1)
    index = int(idx_str)
    if stem == "00_开场":
        return index, stem, "opening", "开场"
    if stem.endswith("_连麦"):
        return index, stem, "call", rest[: -len("_连麦")]
    if stem.endswith("_评论"):
        return index, stem, "comment", rest[: -len("_评论")]
    raise ValueError(f"Unknown title shape: {filename}")


def speaker_names_for_kind(kind: str) -> dict[str, str]:
    if kind == "call":
        return {"host": "曲曲", "guest": "嘉宾"}
    return {"host": "曲曲"}


def speaker_ids_for_kind(kind: str) -> list[str]:
    if kind == "call":
        return ["host", "guest"]
    return ["host"]


def sentence_from_old(sentence: dict, kind: str) -> dict:
    raw_speaker = sentence.get("speaker", "HOST")
    speaker_id = "guest" if raw_speaker == "GUEST" and kind == "call" else "host"
    speaker_name = "嘉宾" if speaker_id == "guest" else "曲曲"
    return {
        "speaker_id": speaker_id,
        "speaker_name": speaker_name,
        "start": float(sentence["start"]),
        "end": float(sentence["end"]),
        "text": sentence["text"],
    }


def convert_group11_file(path: Path, split_lookup: dict[str, dict]) -> None:
    old = json.loads(path.read_text())
    index, title, kind, persona = title_parts(path.name)
    split = split_lookup[path.name]
    source_file = Path(old["source_file"]).name
    sentences = [sentence_from_old(s, kind) for s in old["sentences"]]
    meta = {
        "source_file": source_file,
        "index": index,
        "kind": kind,
        "persona": persona,
        "title": title,
        "start": float(split["start"]),
        "end": float(split["end"]),
        "start_ts": ts(split["start"]),
        "end_ts": ts(split["end"]),
        "raw_segment_count": int(split["segments"]),
        "speaker_ids": speaker_ids_for_kind(kind),
        "speaker_names": speaker_names_for_kind(kind),
        "sentence_count": len(sentences),
        "notes": old.get("qa", {}).get("notes")
        or (
            "由旧版 range/speakers 结构统一迁移到 formal meta+sentences schema。"
            if kind == "call"
            else "由旧版 range 结构统一迁移到 formal meta+sentences schema。"
        ),
    }
    normalized = {"meta": meta, "sentences": sentences}
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")


def normalize_group10_redundant_meta(path: Path) -> None:
    obj = json.loads(path.read_text())
    meta = obj["meta"]
    meta.pop("speaker_id", None)
    meta.pop("speaker_name", None)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def validate_file(path: Path) -> None:
    obj = json.loads(path.read_text())
    assert set(obj.keys()) == {"meta", "sentences"}, path
    meta = obj["meta"]
    sentences = obj["sentences"]
    expected_meta = {
        "source_file",
        "index",
        "kind",
        "persona",
        "title",
        "start",
        "end",
        "start_ts",
        "end_ts",
        "raw_segment_count",
        "speaker_ids",
        "speaker_names",
        "sentence_count",
        "notes",
    }
    assert set(meta.keys()) == expected_meta, (path, sorted(meta.keys()))
    assert meta["sentence_count"] == len(sentences), path
    kind = meta["kind"]
    allowed = {"opening": {"host"}, "comment": {"host"}, "call": {"host", "guest"}}[kind]
    if kind == "call":
        assert meta["speaker_ids"] == ["host", "guest"], path
        assert meta["speaker_names"] == {"host": "曲曲", "guest": "嘉宾"}, path
    else:
        assert meta["speaker_ids"] == ["host"], path
        assert meta["speaker_names"] == {"host": "曲曲"}, path
    for sentence in sentences:
        assert set(sentence.keys()) == {"speaker_id", "speaker_name", "start", "end", "text"}, path
        assert sentence["speaker_id"] in allowed, (path, sentence)
        if sentence["speaker_id"] == "host":
            assert sentence["speaker_name"] == "曲曲", (path, sentence)
        else:
            assert sentence["speaker_name"] == "嘉宾", (path, sentence)


def main() -> None:
    assert SCHEMA_PATH.exists(), SCHEMA_PATH
    split_summary = json.loads((GROUP11 / "_split_summary.json").read_text())
    split_lookup = {item["file"]: item for item in split_summary["parts"]}

    converted = []
    for path in sorted(GROUP11.glob("*.json")):
        if path.name.startswith("_"):
            continue
        convert_group11_file(path, split_lookup)
        converted.append(path)

    cleaned = []
    for name in GROUP10_REDUNDANT:
        path = GROUP10 / name
        normalize_group10_redundant_meta(path)
        cleaned.append(path)

    for path in converted + cleaned:
        validate_file(path)

    print("converted_group11", len(converted))
    print("cleaned_group10_redundant", len(cleaned))


if __name__ == "__main__":
    main()
