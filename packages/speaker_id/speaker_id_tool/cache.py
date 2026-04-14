from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


EMBEDDING_CACHE_VERSION = 1


@dataclass(slots=True)
class CachedMeasurement:
    vector: np.ndarray
    duration_sec: float
    rms: float


class EmbeddingCache:
    def __init__(self, root: Path, backend_name: str, backend_identity: dict):
        self.root = root
        self.backend_name = backend_name
        self.backend_identity = backend_identity
        self.hit_count = 0
        self.miss_count = 0
        self.write_count = 0

    def snapshot(self) -> dict:
        lookups = self.hit_count + self.miss_count
        return {
            "root": str(self.root),
            "backend": self.backend_name,
            "hits": self.hit_count,
            "misses": self.miss_count,
            "writes": self.write_count,
            "lookups": lookups,
            "hit_rate": float(self.hit_count / lookups) if lookups else None,
        }

    def load(
        self,
        audio_path: Path,
        sentence_index: int,
        start: float,
        end: float,
        text: str,
    ) -> CachedMeasurement | None:
        entry_path = self._entry_path(audio_path, sentence_index, start, end, text)
        if not entry_path.exists():
            self.miss_count += 1
            return None
        try:
            with np.load(entry_path, allow_pickle=False) as payload:
                vector = payload["vector"].astype(np.float32)
                duration_sec = float(payload["duration_sec"])
                rms = float(payload["rms"])
        except Exception:
            self.miss_count += 1
            return None
        self.hit_count += 1
        return CachedMeasurement(vector=vector, duration_sec=duration_sec, rms=rms)

    def save(
        self,
        audio_path: Path,
        sentence_index: int,
        start: float,
        end: float,
        text: str,
        vector: np.ndarray,
        duration_sec: float,
        rms: float,
    ) -> None:
        entry_path = self._entry_path(audio_path, sentence_index, start, end, text)
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=entry_path.parent, suffix=".npz", delete=False) as handle:
            np.savez_compressed(
                handle,
                vector=np.asarray(vector, dtype=np.float32),
                duration_sec=np.float32(duration_sec),
                rms=np.float32(rms),
            )
            temp_path = Path(handle.name)
        temp_path.replace(entry_path)
        self.write_count += 1

    def _entry_path(
        self,
        audio_path: Path,
        sentence_index: int,
        start: float,
        end: float,
        text: str,
    ) -> Path:
        key_payload = {
            "cache_version": EMBEDDING_CACHE_VERSION,
            "backend": self.backend_name,
            "backend_identity": self.backend_identity,
            "audio_path": str(audio_path.resolve()),
            "audio_mtime_ns": audio_path.stat().st_mtime_ns,
            "sentence_index": sentence_index,
            "start": round(float(start), 6),
            "end": round(float(end), 6),
            "text": text.strip(),
        }
        digest = hashlib.sha1(
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.root / self.backend_name / digest[:2] / f"{digest}.npz"


def summarize_embedding_cache(root: Path, backend_name: str | None = None) -> dict:
    target = root / backend_name if backend_name else root
    if not target.exists():
        return {
            "path": str(target),
            "backend": backend_name,
            "exists": False,
            "entry_count": 0,
            "total_bytes": 0,
        }
    files = list(target.rglob("*.npz"))
    return {
        "path": str(target),
        "backend": backend_name,
        "exists": True,
        "entry_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
    }


def clear_embedding_cache(root: Path, backend_name: str | None = None) -> dict:
    before = summarize_embedding_cache(root, backend_name)
    target = Path(before["path"])
    if target.exists():
        shutil.rmtree(target)
    return {
        **before,
        "cleared": True,
    }
