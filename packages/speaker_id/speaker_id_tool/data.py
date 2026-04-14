from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PartRecord:
    part_path: Path
    transcript_path: Path
    audio_path: Path
    meta: dict
    sentences: list[dict]
    raw_segments: list[dict]


class DataIndex:
    def __init__(self, downloads_root: Path, transcripts_root: Path):
        self.downloads_root = downloads_root
        self.transcripts_root = transcripts_root
        self._audio_by_name = self._build_index(downloads_root, suffix=".mp3")
        self._transcript_by_name = self._build_index(transcripts_root, suffix=".json")

    @staticmethod
    def _build_index(root: Path, suffix: str) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for path in root.rglob(f"*{suffix}"):
            index.setdefault(path.name, path)
        return index

    def resolve_audio(self, source_file: str) -> Path:
        candidate = Path(source_file).with_suffix(".mp3").name
        if candidate not in self._audio_by_name:
            raise FileNotFoundError(f"Audio not found for source_file={source_file!r}")
        return self._audio_by_name[candidate]

    def resolve_transcript(self, source_file: str) -> Path:
        candidate = Path(source_file).name
        if candidate not in self._transcript_by_name:
            raise FileNotFoundError(f"Transcript not found for source_file={source_file!r}")
        return self._transcript_by_name[candidate]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def iter_call_parts(parts_root: Path):
    for path in sorted(parts_root.rglob("*_连麦.json")):
        yield path


def load_part_record(part_path: Path, data_index: DataIndex) -> PartRecord:
    payload = load_json(part_path)
    meta = payload["meta"]
    transcript_path = data_index.resolve_transcript(meta["source_file"])
    transcript_payload = load_json(transcript_path)
    audio_path = data_index.resolve_audio(meta["source_file"])
    return PartRecord(
        part_path=part_path,
        transcript_path=transcript_path,
        audio_path=audio_path,
        meta=meta,
        sentences=payload.get("sentences", []),
        raw_segments=transcript_payload.get("segments", []),
    )
