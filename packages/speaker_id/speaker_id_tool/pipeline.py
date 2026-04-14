from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np
from rich.console import Console
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score

from .backends import EmbeddingBackend
from .cache import EmbeddingCache
from .config import (
    CLUSTER_MIN_SEGMENTS,
    DEFAULT_HOST_BANK_PATH,
    EDGE_LOW_CONFIDENCE,
    EDGE_SHORT_UTTERANCE_SEC,
    MAX_SEGMENT_SEC,
    MIXED_SENTENCE_MAX_RUNS,
    MIXED_SENTENCE_MIN_DURATION_SEC,
    MIXED_SENTENCE_MIN_MARGIN,
    MIXED_SENTENCE_MIN_RUN_DURATION_SEC,
    MIXED_SENTENCE_MIN_RUN_WINDOWS,
    MIXED_SENTENCE_MIN_WINDOWS,
    MIXED_SENTENCE_SMOOTHING_PASSES,
    MIN_RMS,
    MIN_SEGMENT_SEC,
    OPENING_HOST_MAX_SENTENCES,
    OPENING_HOST_WINDOW_SEC,
    OVERLAP_MIN_SECONDS,
    OVERLAP_CONFIDENCE_CAP,
    OVERLAP_CONFIDENCE_SCALE,
    OVERLAP_WINDOW_PADDING,
    SAMPLE_RATE,
    WINDOW_REFINE_DOMINANT_RATIO,
    WINDOW_REFINE_HOP_SEC,
    WINDOW_REFINE_MAX_CLASS_RATIO,
    WINDOW_REFINE_MAX_SILHOUETTE,
    WINDOW_REFINE_MIN_CENTER_GAP,
    WINDOW_REFINE_MIN_SENTENCES,
    WINDOW_REFINE_MIN_WINDOWS,
    WINDOW_REFINE_MIN_WINDOW_SEC,
    WINDOW_REFINE_SINGLE_WINDOW_MARGIN,
    WINDOW_REFINE_WINDOW_SEC,
)
from .data import DataIndex, PartRecord, iter_call_parts, load_part_record
from .features import cosine_similarity, load_audio_range, load_audio_slice, waveform_rms

console = Console()
TEXT_TRANSLATION = str.maketrans("", "", " \t\r\n,，。.!！？?、:：;；\"'“”‘’（）()-[]【】")
HOST_GREETING_PREFIXES = ("哈喽", "你好", "嗨", "喂", "hello", "hi")
HOST_PROMPT_CUES = (
    "你说",
    "你讲",
    "请讲",
    "说吧",
    "说说",
    "讲吧",
    "讲讲",
    "慢慢说",
    "听得到",
    "能听到",
    "在吗",
    "在线吗",
)


@dataclass(slots=True)
class SegmentMeasurement:
    sentence_index: int
    start: float
    end: float
    vector: np.ndarray
    rms: float
    duration_sec: float
    usable: bool


@dataclass(slots=True)
class SentencePrediction:
    sentence_index: int
    start: float
    end: float
    duration_sec: float
    text: str
    original_speaker_id: str | None
    predicted_speaker_id: str
    confidence: float
    overlap_suspected: bool
    feature_usable: bool
    host_similarity: float
    guest_similarity: float
    split_applied: bool = False
    corrected_segments: list["CorrectedSegment"] = field(default_factory=list)


@dataclass(slots=True)
class CorrectedSegment:
    source_sentence_index: int
    segment_index: int
    start: float
    end: float
    duration_sec: float
    text: str
    predicted_speaker_id: str
    confidence: float
    kind: str


@dataclass(slots=True)
class WindowMeasurement:
    sentence_index: int
    window_index: int
    start: float
    end: float
    duration_sec: float
    vector: np.ndarray
    host_similarity: float


@dataclass(slots=True)
class AudioContext:
    start: float
    end: float
    waveform: np.ndarray


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def make_audio_context(record: PartRecord) -> AudioContext | None:
    if not record.sentences:
        return None
    start = min(float(sentence["start"]) for sentence in record.sentences)
    end = max(float(sentence["end"]) for sentence in record.sentences)
    waveform = load_audio_range(record.audio_path, start, end)
    return AudioContext(start=start, end=end, waveform=waveform)


def build_host_bank(
    parts_root: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    output_path: Path = DEFAULT_HOST_BANK_PATH,
    max_parts: int = 300,
    max_segments: int = 1200,
    embedding_cache: EmbeddingCache | None = None,
) -> dict:
    vectors: list[np.ndarray] = []
    part_count = 0
    for part_path in iter_call_parts(parts_root):
        if part_count >= max_parts or len(vectors) >= max_segments:
            break
        try:
            record = load_part_record(part_path, data_index)
        except Exception as exc:
            console.print(f"[yellow]skip host-bank[/yellow] {part_path}: {exc}")
            continue
        audio_context = make_audio_context(record)
        part_count += 1
        host_sentences = [
            (idx, sentence)
            for idx, sentence in enumerate(record.sentences)
            if sentence.get("speaker_id") == "host"
            and MIN_SEGMENT_SEC <= sentence_duration(sentence) <= MAX_SEGMENT_SEC
            and sentence.get("text", "").strip()
        ]
        host_sentences.sort(key=lambda item: sentence_duration(item[1]), reverse=True)
        for idx, sentence in host_sentences[:3]:
            if len(vectors) >= max_segments:
                break
            measurement = measure_sentence(
                record,
                idx,
                sentence,
                backend,
                embedding_cache,
                audio_context,
            )
            if measurement.usable:
                vectors.append(measurement.vector)

    if not vectors:
        raise RuntimeError("No usable host segments found to build host bank.")

    centroid = mean_vector(vectors)
    payload = {
        "version": 1,
        "feature_backend": backend.name,
        "backend_config": backend.export_config(),
        "segment_count": len(vectors),
        "part_count": part_count,
        "centroid": centroid.tolist(),
    }
    if embedding_cache is not None:
        payload["embedding_cache"] = embedding_cache.snapshot()
    ensure_output_dir(output_path.parent)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def load_host_bank(path: Path = DEFAULT_HOST_BANK_PATH) -> dict:
    return json.loads(path.read_text())


def analyze_part(
    part_path: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    host_bank: dict,
    output_dir: Path,
    embedding_cache: EmbeddingCache | None = None,
) -> dict:
    record = load_part_record(part_path, data_index)
    audio_context = make_audio_context(record)
    if host_bank.get("feature_backend") != backend.name:
        raise ValueError(
            f"Host bank backend mismatch: bank={host_bank.get('feature_backend')} runtime={backend.name}"
        )
    measurements = [
        measure_sentence(record, idx, sentence, backend, embedding_cache, audio_context)
        for idx, sentence in enumerate(record.sentences)
    ]
    usable_measurements = [item for item in measurements if item.usable]
    host_centroid = np.asarray(host_bank["centroid"], dtype=np.float32)

    cluster_payload = cluster_sentences(record, usable_measurements, host_centroid)
    predictions, refinement_summary = predict_sentences(
        record,
        measurements,
        cluster_payload,
        backend,
        host_centroid,
        embedding_cache,
        audio_context,
    )

    part_output_dir = output_dir / sanitize_path(record.part_path.stem)
    ensure_output_dir(part_output_dir)
    report = {
        "part_path": str(record.part_path),
        "audio_path": str(record.audio_path),
        "transcript_path": str(record.transcript_path),
        "feature_backend": backend.name,
        "meta": record.meta,
        "cluster_summary": cluster_payload["summary"],
        "predictions": [asdict(item) for item in predictions],
        "corrected_summary": summarize_corrected_segments(predictions),
        "corrected_sentences": flatten_corrected_segments(predictions),
        "refinement_summary": refinement_summary,
    }
    if embedding_cache is not None:
        report["embedding_cache"] = embedding_cache.snapshot()
    (part_output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def analyze_dataset(
    parts_root: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    host_bank: dict,
    output_dir: Path,
    limit: int | None = None,
    embedding_cache: EmbeddingCache | None = None,
) -> list[dict]:
    reports = []
    for idx, part_path in enumerate(iter_call_parts(parts_root), start=1):
        if limit is not None and idx > limit:
            break
        try:
            report = analyze_part(
                part_path, data_index, backend, host_bank, output_dir / "dataset", embedding_cache
            )
            reports.append(
                {
                    "part_path": report["part_path"],
                    "host_count": sum(
                        1 for item in report["predictions"] if item["predicted_speaker_id"] == "host"
                    ),
                    "guest_count": sum(
                        1 for item in report["predictions"] if item["predicted_speaker_id"] == "guest"
                    ),
                    "overlap_count": sum(
                        1 for item in report["predictions"] if item["overlap_suspected"]
                    ),
                }
            )
        except Exception as exc:
            reports.append({"part_path": str(part_path), "error": str(exc)})

    ensure_output_dir(output_dir)
    (output_dir / "dataset_summary.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    return reports


def summarize_predictions(predictions: list[SentencePrediction]) -> dict:
    usable = [item for item in predictions if item.original_speaker_id in {"host", "guest"}]
    correct = sum(1 for item in usable if item.original_speaker_id == item.predicted_speaker_id)
    total = len(usable)
    return {
        "correct": correct,
        "total": total,
        "agreement": (correct / total) if total else None,
        "low_confidence_count": sum(1 for item in predictions if item.confidence < 0.6),
        "overlap_count": sum(1 for item in predictions if item.overlap_suspected),
    }


def flatten_corrected_segments(predictions: list[SentencePrediction]) -> list[dict]:
    flattened: list[dict] = []
    for item in predictions:
        if item.corrected_segments:
            segments = item.corrected_segments
        else:
            segments = [build_default_corrected_segment(item)]
        for segment in segments:
            flattened.append(asdict(segment))
    flattened.sort(key=lambda segment: (segment["start"], segment["end"], segment["source_sentence_index"]))
    return flattened


def summarize_corrected_segments(predictions: list[SentencePrediction]) -> dict:
    segments = flatten_corrected_segments(predictions)
    return {
        "segment_count": len(segments),
        "speaker_counts": {
            "host": sum(1 for item in segments if item["predicted_speaker_id"] == "host"),
            "guest": sum(1 for item in segments if item["predicted_speaker_id"] == "guest"),
            "unknown": sum(
                1 for item in segments if item["predicted_speaker_id"] not in {"host", "guest"}
            ),
        },
        "split_sentence_count": sum(1 for item in predictions if item.split_applied),
    }


def compare_part_predictions(
    part_path: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    host_bank: dict,
    embedding_cache: EmbeddingCache | None = None,
) -> dict:
    record = load_part_record(part_path, data_index)
    audio_context = make_audio_context(record)
    if host_bank.get("feature_backend") != backend.name:
        raise ValueError(
            f"Host bank backend mismatch: bank={host_bank.get('feature_backend')} runtime={backend.name}"
        )
    measurements = [
        measure_sentence(record, idx, sentence, backend, embedding_cache, audio_context)
        for idx, sentence in enumerate(record.sentences)
    ]
    usable_measurements = [item for item in measurements if item.usable]
    host_centroid = np.asarray(host_bank["centroid"], dtype=np.float32)
    cluster_payload = cluster_sentences(record, usable_measurements, host_centroid)
    base_predictions = build_base_predictions(record, measurements, cluster_payload)
    before_predictions = postprocess_predictions(base_predictions)
    after_predictions, refinement_summary = apply_window_vote_refinement(
        record=record,
        measurements=measurements,
        predictions=before_predictions,
        cluster_payload=cluster_payload,
        backend=backend,
        host_centroid=host_centroid,
        embedding_cache=embedding_cache,
        audio_context=audio_context,
    )

    original_sentences = []
    for idx, sentence in enumerate(record.sentences):
        original_sentences.append(
            {
                "sentence_index": idx,
                "start": float(sentence["start"]),
                "end": float(sentence["end"]),
                "duration_sec": float(sentence_duration(sentence)),
                "text": sentence.get("text", ""),
                "speaker_id": sentence.get("speaker_id"),
            }
        )

    changed_sentences = []
    for before_item, after_item in zip(before_predictions, after_predictions, strict=True):
        if (
            before_item.predicted_speaker_id != after_item.predicted_speaker_id
            or abs(before_item.confidence - after_item.confidence) > 1e-9
            or after_item.split_applied
        ):
            changed_sentences.append(
                {
                    "sentence_index": before_item.sentence_index,
                    "text": before_item.text,
                    "original_speaker_id": before_item.original_speaker_id,
                    "before_predicted": before_item.predicted_speaker_id,
                    "after_predicted": after_item.predicted_speaker_id,
                    "before_confidence": before_item.confidence,
                    "after_confidence": after_item.confidence,
                    "overlap_suspected": after_item.overlap_suspected,
                    "split_applied": after_item.split_applied,
                    "corrected_segment_count": len(after_item.corrected_segments) or 1,
                }
            )

    payload = {
        "part_path": str(record.part_path),
        "audio_path": str(record.audio_path),
        "transcript_path": str(record.transcript_path),
        "feature_backend": backend.name,
        "meta": record.meta,
        "cluster_summary": cluster_payload["summary"],
        "original": {
            "sentence_count": len(original_sentences),
            "speaker_counts": {
                "host": sum(1 for item in original_sentences if item["speaker_id"] == "host"),
                "guest": sum(1 for item in original_sentences if item["speaker_id"] == "guest"),
                "unknown": sum(
                    1
                    for item in original_sentences
                    if item["speaker_id"] not in {"host", "guest"}
                ),
            },
            "sentences": original_sentences,
        },
        "before": {
            "summary": summarize_predictions(before_predictions),
            "predictions": [asdict(item) for item in before_predictions],
        },
        "after": {
            "summary": summarize_predictions(after_predictions),
            "predictions": [asdict(item) for item in after_predictions],
            "corrected_summary": summarize_corrected_segments(after_predictions),
            "corrected_sentences": flatten_corrected_segments(after_predictions),
        },
        "changed_sentences": changed_sentences,
        "refinement_summary": refinement_summary,
    }
    if embedding_cache is not None:
        payload["embedding_cache"] = embedding_cache.snapshot()
    return payload


def warm_cache_for_part(
    part_path: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    embedding_cache: EmbeddingCache,
) -> dict:
    record = load_part_record(part_path, data_index)
    audio_context = make_audio_context(record)
    measurements = [
        measure_sentence(record, idx, sentence, backend, embedding_cache, audio_context)
        for idx, sentence in enumerate(record.sentences)
    ]
    return {
        "part_path": str(record.part_path),
        "sentence_count": len(record.sentences),
        "usable_segment_count": sum(1 for item in measurements if item.usable),
        "cache": embedding_cache.snapshot(),
    }


def warm_cache_for_dataset(
    parts_root: Path,
    data_index: DataIndex,
    backend: EmbeddingBackend,
    embedding_cache: EmbeddingCache,
    limit: int | None = None,
) -> list[dict]:
    reports = []
    for idx, part_path in enumerate(iter_call_parts(parts_root), start=1):
        if limit is not None and idx > limit:
            break
        try:
            reports.append(
                warm_cache_for_part(
                    part_path=part_path,
                    data_index=data_index,
                    backend=backend,
                    embedding_cache=embedding_cache,
                )
            )
        except Exception as exc:
            reports.append({"part_path": str(part_path), "error": str(exc)})
    return reports


def cluster_sentences(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    host_centroid: np.ndarray,
) -> dict:
    if not measurements:
        return {
            "summary": {
                "mode": "empty",
                "usable_segment_count": 0,
            },
            "host_cluster_centroid": host_centroid,
            "guest_cluster_centroid": host_centroid * 0,
            "assignments": {},
        }

    vectors = np.vstack([item.vector for item in measurements])
    assignments: dict[int, str] = {}

    if len(measurements) < CLUSTER_MIN_SEGMENTS:
        centroid = mean_vector([item.vector for item in measurements])
        host_sim = cosine_similarity(centroid, host_centroid)
        speaker = "host" if host_sim >= 0.45 else "guest"
        for item in measurements:
            assignments[item.sentence_index] = speaker
        guest_centroid = np.zeros_like(host_centroid)
        summary = {
            "mode": "few-segments",
            "usable_segment_count": len(measurements),
            "silhouette": None,
            "host_similarity": host_sim,
        }
        return {
            "summary": summary,
            "host_cluster_centroid": centroid if speaker == "host" else host_centroid,
            "guest_cluster_centroid": guest_centroid if speaker == "host" else centroid,
            "assignments": assignments,
        }

    model = AgglomerativeClustering(n_clusters=2, metric="cosine", linkage="average")
    labels = model.fit_predict(vectors)
    silhouette = float(silhouette_score(vectors, labels, metric="cosine"))

    cluster0 = mean_vector(vectors[labels == 0])
    cluster1 = mean_vector(vectors[labels == 1])
    cluster0_host = cosine_similarity(cluster0, host_centroid)
    cluster1_host = cosine_similarity(cluster1, host_centroid)
    host_label = choose_host_label(record, measurements, labels, cluster0_host, cluster1_host)
    if host_label == 0:
        label_to_speaker = {0: "host", 1: "guest"}
        host_cluster_centroid = cluster0
        guest_cluster_centroid = cluster1
    else:
        label_to_speaker = {0: "guest", 1: "host"}
        host_cluster_centroid = cluster1
        guest_cluster_centroid = cluster0

    if silhouette < 0.03:
        dominant = "host" if max(cluster0_host, cluster1_host) >= 0.45 else "guest"
        for item in measurements:
            assignments[item.sentence_index] = dominant
        summary = {
            "mode": "fallback-single-speaker",
            "usable_segment_count": len(measurements),
            "silhouette": silhouette,
        }
        return {
            "summary": summary,
            "host_cluster_centroid": host_cluster_centroid if dominant == "host" else host_centroid,
            "guest_cluster_centroid": guest_cluster_centroid if dominant == "guest" else np.zeros_like(host_centroid),
            "assignments": assignments,
        }

    for item, label in zip(measurements, labels, strict=True):
        assignments[item.sentence_index] = label_to_speaker[int(label)]

    summary = {
        "mode": "two-speaker-cluster",
        "usable_segment_count": len(measurements),
        "silhouette": silhouette,
        "cluster0_host_similarity": cluster0_host,
        "cluster1_host_similarity": cluster1_host,
    }
    return {
        "summary": summary,
        "host_cluster_centroid": host_cluster_centroid,
        "guest_cluster_centroid": guest_cluster_centroid,
        "assignments": assignments,
    }


def predict_sentences(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    cluster_payload: dict,
    backend: EmbeddingBackend,
    host_centroid: np.ndarray,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> tuple[list[SentencePrediction], dict]:
    predictions = build_base_predictions(record, measurements, cluster_payload)
    return finalize_predictions(
        record=record,
        measurements=measurements,
        base_predictions=predictions,
        cluster_payload=cluster_payload,
        backend=backend,
        host_centroid=host_centroid,
        embedding_cache=embedding_cache,
        audio_context=audio_context,
    )


def build_base_predictions(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    cluster_payload: dict,
) -> list[SentencePrediction]:
    assignments = cluster_payload["assignments"]
    host_cluster_centroid = cluster_payload["host_cluster_centroid"]
    guest_cluster_centroid = cluster_payload["guest_cluster_centroid"]
    predictions: list[SentencePrediction] = []

    for idx, sentence in enumerate(record.sentences):
        measurement = measurements[idx]
        host_sim = cosine_similarity(measurement.vector, host_cluster_centroid)
        guest_sim = cosine_similarity(measurement.vector, guest_cluster_centroid)
        if idx in assignments:
            speaker = assignments[idx]
        else:
            speaker = "host" if host_sim >= guest_sim else "guest"
        margin = abs(host_sim - guest_sim)
        confidence = float(1 / (1 + np.exp(-20.0 * (margin - 0.02))))
        predictions.append(
            SentencePrediction(
                sentence_index=idx,
                start=float(sentence["start"]),
                end=float(sentence["end"]),
                duration_sec=float(sentence_duration(sentence)),
                text=sentence.get("text", ""),
                original_speaker_id=sentence.get("speaker_id"),
                predicted_speaker_id=speaker,
                confidence=confidence,
                overlap_suspected=is_overlap_suspected(record.raw_segments, sentence["start"], sentence["end"]),
                feature_usable=measurement.usable,
                host_similarity=host_sim,
                guest_similarity=guest_sim,
            )
        )
    return predictions


def measure_sentence(
    record: PartRecord,
    sentence_index: int,
    sentence: dict,
    backend: EmbeddingBackend,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> SegmentMeasurement:
    start = float(sentence["start"])
    end = float(sentence["end"])
    text = sentence.get("text", "")
    vector, duration_sec, rms = extract_segment_features(
        audio_path=record.audio_path,
        segment_key=sentence_index,
        start=start,
        end=end,
        text=text,
        backend=backend,
        embedding_cache=embedding_cache,
        audio_context=audio_context,
    )
    usable = (
        MIN_SEGMENT_SEC <= duration_sec <= MAX_SEGMENT_SEC
        and rms >= MIN_RMS
        and text.strip() != ""
    )
    return SegmentMeasurement(
        sentence_index=sentence_index,
        start=start,
        end=end,
        vector=vector,
        rms=rms,
        duration_sec=duration_sec,
        usable=usable,
    )


def extract_segment_features(
    audio_path: Path,
    segment_key: int,
    start: float,
    end: float,
    text: str,
    backend: EmbeddingBackend,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> tuple[np.ndarray, float, float]:
    cached = None
    if embedding_cache is not None:
        cached = embedding_cache.load(audio_path, segment_key, start, end, text)
    if cached is not None:
        return cached.vector, cached.duration_sec, cached.rms

    waveform = load_audio_slice(
        audio_path,
        start,
        end,
        preloaded_waveform=audio_context.waveform if audio_context is not None else None,
        preloaded_start=audio_context.start if audio_context is not None else 0.0,
    )
    vector = backend.extract(waveform, SAMPLE_RATE)
    duration_sec = float(waveform.size / SAMPLE_RATE)
    rms = waveform_rms(waveform)
    if embedding_cache is not None:
        embedding_cache.save(
            audio_path,
            segment_key,
            start,
            end,
            text,
            vector,
            duration_sec,
            rms,
        )
    return vector, duration_sec, rms


def mean_vector(vectors: list[np.ndarray] | np.ndarray) -> np.ndarray:
    matrix = np.vstack(vectors)
    centroid = matrix.mean(axis=0)
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 0 else centroid


def sentence_duration(sentence: dict) -> float:
    return float(sentence["end"]) - float(sentence["start"])


def is_overlap_suspected(raw_segments: list[dict], start: float, end: float) -> bool:
    left = start - OVERLAP_WINDOW_PADDING
    right = end + OVERLAP_WINDOW_PADDING
    active = [
        seg
        for seg in raw_segments
        if float(seg.get("end", 0)) > left and float(seg.get("start", 0)) < right
    ]
    for idx, first in enumerate(active):
        for second in active[idx + 1 :]:
            if first.get("speaker") == second.get("speaker"):
                continue
            overlap = min(float(first["end"]), float(second["end"])) - max(
                float(first["start"]), float(second["start"])
            )
            if overlap >= OVERLAP_MIN_SECONDS:
                return True
    return False


def sanitize_path(name: str) -> str:
    keep = []
    for char in name:
        keep.append(char if char.isalnum() or char in {"-", "_"} else "_")
    return "".join(keep).strip("_") or "part"


def choose_host_label(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    labels: np.ndarray,
    cluster0_host: float,
    cluster1_host: float,
) -> int:
    usable_original = []
    for item, label in zip(measurements, labels, strict=True):
        original = record.sentences[item.sentence_index].get("speaker_id")
        if original in {"host", "guest"}:
            usable_original.append((int(label), original))
    if usable_original:
        direct_score = sum(1 for label, original in usable_original if (label == 0 and original == "host") or (label == 1 and original == "guest"))
        flipped_score = sum(1 for label, original in usable_original if (label == 1 and original == "host") or (label == 0 and original == "guest"))
        if direct_score != flipped_score:
            return 0 if direct_score >= flipped_score else 1

    host_margin = abs(cluster0_host - cluster1_host)
    if host_margin >= 0.02:
        return 0 if cluster0_host >= cluster1_host else 1

    earliest = min(item.start for item in measurements)
    early_limit = earliest + 45.0
    early_counts = {0: 0, 1: 0}
    for item, label in zip(measurements, labels, strict=True):
        if item.start <= early_limit:
            early_counts[int(label)] += 1
    if early_counts[0] != early_counts[1]:
        return 0 if early_counts[0] >= early_counts[1] else 1
    return 0 if cluster0_host >= cluster1_host else 1


def smooth_predictions(predictions: list[SentencePrediction]) -> list[SentencePrediction]:
    if len(predictions) < 3:
        return predictions
    smoothed = list(predictions)
    for idx in range(1, len(smoothed) - 1):
        prev_item = smoothed[idx - 1]
        item = smoothed[idx]
        next_item = smoothed[idx + 1]
        if (
            item.duration_sec <= 1.0
            and (not item.feature_usable or item.confidence < 0.55)
            and prev_item.predicted_speaker_id == next_item.predicted_speaker_id
            and prev_item.predicted_speaker_id != item.predicted_speaker_id
        ):
            smoothed[idx] = replace(
                item,
                predicted_speaker_id=prev_item.predicted_speaker_id,
                confidence=max(item.confidence, 0.58),
            )
    return smoothed


def postprocess_predictions(predictions: list[SentencePrediction]) -> list[SentencePrediction]:
    adjusted = apply_overlap_confidence_adjustment(predictions)
    adjusted = smooth_predictions(adjusted)
    adjusted = apply_opening_host_prior(adjusted)
    adjusted = smooth_edge_predictions(adjusted)
    return adjusted


def finalize_predictions(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    base_predictions: list[SentencePrediction],
    cluster_payload: dict,
    backend: EmbeddingBackend,
    host_centroid: np.ndarray,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> tuple[list[SentencePrediction], dict]:
    adjusted = postprocess_predictions(base_predictions)
    refined, refinement_summary = apply_window_vote_refinement(
        record=record,
        measurements=measurements,
        predictions=adjusted,
        cluster_payload=cluster_payload,
        backend=backend,
        host_centroid=host_centroid,
        embedding_cache=embedding_cache,
        audio_context=audio_context,
    )
    return refined, refinement_summary


def apply_window_vote_refinement(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    predictions: list[SentencePrediction],
    cluster_payload: dict,
    backend: EmbeddingBackend,
    host_centroid: np.ndarray,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> tuple[list[SentencePrediction], dict]:
    summary = build_window_refinement_summary(
        record=record,
        measurements=measurements,
        predictions=predictions,
        cluster_payload=cluster_payload,
        backend=backend,
        host_centroid=host_centroid,
        embedding_cache=embedding_cache,
        audio_context=audio_context,
    )
    if summary is None:
        annotated, split_indices = attach_corrected_segments(record, predictions, None)
        return annotated, {
            "applied": False,
            "reason": "insufficient_window_signal",
            "should_apply": False,
            "split_sentence_indices": split_indices,
            "split_sentence_count": len(split_indices),
            "changed_indices": [],
        }

    refined = list(predictions)
    changed_indices: list[int] = []
    if summary["should_apply"]:
        for idx, item in enumerate(refined):
            vote = summary["sentence_votes"].get(item.sentence_index)
            if vote is None:
                continue
            target = vote["dominant_speaker"]
            if target is None:
                continue
            should_override = False
            if vote["window_count"] >= 2 and vote["dominant_ratio"] >= WINDOW_REFINE_DOMINANT_RATIO:
                should_override = True
            elif (
                vote["window_count"] == 1
                and abs(vote["mean_host_similarity"] - summary["score_threshold"]) >= WINDOW_REFINE_SINGLE_WINDOW_MARGIN
            ):
                should_override = True
            if not should_override:
                continue
            confidence = min(
                0.96,
                max(
                    0.58,
                    0.45 + 0.35 * vote["dominant_ratio"] + 0.6 * vote["threshold_distance"],
                ),
            )
            if (
                item.predicted_speaker_id != target
                or abs(item.confidence - confidence) > 1e-9
            ):
                changed_indices.append(item.sentence_index)
            refined[idx] = replace(item, predicted_speaker_id=target, confidence=confidence)

    refined, split_indices = attach_corrected_segments(record, refined, summary)

    updated_summary = {
        **summary,
        "applied": bool(summary["should_apply"]),
        "changed_indices": changed_indices,
        "split_sentence_indices": split_indices,
        "split_sentence_count": len(split_indices),
    }
    return refined, updated_summary


def build_window_refinement_summary(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    predictions: list[SentencePrediction],
    cluster_payload: dict,
    backend: EmbeddingBackend,
    host_centroid: np.ndarray,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> dict | None:
    windows = collect_window_measurements(
        record,
        measurements,
        backend,
        host_centroid,
        embedding_cache,
        audio_context,
    )
    if len(windows) < WINDOW_REFINE_MIN_WINDOWS:
        return None
    host_scores = np.asarray([[item.host_similarity] for item in windows], dtype=np.float32)
    model = KMeans(n_clusters=2, n_init=20, random_state=0)
    labels = model.fit_predict(host_scores)
    centers = model.cluster_centers_.reshape(-1)
    center_gap = float(abs(np.max(centers) - np.min(centers)))
    if center_gap < WINDOW_REFINE_MIN_CENTER_GAP:
        return {
            "applied": False,
            "reason": "small_window_center_gap",
            "should_apply": False,
            "window_count": len(windows),
            "center_gap": center_gap,
            "centers": centers.tolist(),
            "changed_indices": [],
            "split_sentence_indices": [],
            "split_sentence_count": 0,
        }

    host_label = int(np.argmax(centers))
    threshold = float(np.mean(centers))
    windows_by_sentence: dict[int, list[WindowMeasurement]] = {}
    labels_by_sentence: dict[int, list[str]] = {}
    for item, label in zip(windows, labels, strict=True):
        windows_by_sentence.setdefault(item.sentence_index, []).append(item)
        labels_by_sentence.setdefault(item.sentence_index, []).append(
            "host" if int(label) == host_label else "guest"
        )

    sentence_votes: dict[int, dict] = {}
    sentence_window_runs: dict[int, list[dict]] = {}
    for idx, item in enumerate(predictions):
        sentence_windows = windows_by_sentence.get(idx, [])
        sentence_labels = labels_by_sentence.get(idx, [])
        if sentence_windows:
            host_votes = sentence_labels.count("host")
            guest_votes = sentence_labels.count("guest")
            dominant_speaker = "host" if host_votes >= guest_votes else "guest"
            dominant_votes = max(host_votes, guest_votes)
            dominant_ratio = dominant_votes / len(sentence_windows)
            mean_host_similarity = float(np.mean([window.host_similarity for window in sentence_windows]))
            sentence_window_runs[idx] = build_sentence_window_runs(
                sentence_windows=sentence_windows,
                threshold=threshold,
                sentence_start=item.start,
                sentence_end=item.end,
            )
        else:
            dominant_speaker = item.predicted_speaker_id
            dominant_ratio = 1.0
            mean_host_similarity = item.host_similarity
            host_votes = int(item.host_similarity >= threshold)
            guest_votes = int(item.host_similarity < threshold)
            sentence_window_runs[idx] = []
        sentence_votes[idx] = {
            "window_count": len(sentence_windows),
            "host_votes": host_votes,
            "guest_votes": guest_votes,
            "dominant_speaker": dominant_speaker,
            "dominant_ratio": float(dominant_ratio),
            "mean_host_similarity": float(mean_host_similarity),
            "threshold_distance": float(abs(mean_host_similarity - threshold)),
        }

    counts = {
        "host": sum(1 for item in predictions if item.predicted_speaker_id == "host"),
        "guest": sum(1 for item in predictions if item.predicted_speaker_id == "guest"),
    }
    total = max(len(predictions), 1)
    max_ratio = max(counts.values()) / total
    silhouette = cluster_payload["summary"].get("silhouette")
    should_apply = (
        len(predictions) >= WINDOW_REFINE_MIN_SENTENCES
        and max_ratio >= WINDOW_REFINE_MAX_CLASS_RATIO
        and (silhouette is None or silhouette <= WINDOW_REFINE_MAX_SILHOUETTE)
    )

    return {
        "applied": False,
        "reason": "degenerate_cluster_distribution" if should_apply else "cluster_not_degenerate",
        "should_apply": should_apply,
        "window_count": len(windows),
        "centers": centers.tolist(),
        "center_gap": center_gap,
        "score_threshold": threshold,
        "predicted_counts_before": counts,
        "max_class_ratio_before": max_ratio,
        "silhouette": silhouette,
        "sentence_votes": sentence_votes,
        "sentence_window_runs": sentence_window_runs,
    }


def attach_corrected_segments(
    record: PartRecord,
    predictions: list[SentencePrediction],
    summary: dict | None,
) -> tuple[list[SentencePrediction], list[int]]:
    runs_by_sentence = summary.get("sentence_window_runs", {}) if summary is not None else {}
    refined: list[SentencePrediction] = []
    split_indices: list[int] = []
    for item in predictions:
        runs = runs_by_sentence.get(item.sentence_index, [])
        corrected_segments, split_applied = build_corrected_segments_for_prediction(
            record=record,
            prediction=item,
            runs=runs,
        )
        if split_applied:
            split_indices.append(item.sentence_index)
        refined.append(
            replace(
                item,
                split_applied=split_applied,
                corrected_segments=corrected_segments,
            )
        )
    return refined, split_indices


def build_corrected_segments_for_prediction(
    record: PartRecord,
    prediction: SentencePrediction,
    runs: list[dict],
) -> tuple[list[CorrectedSegment], bool]:
    if not should_split_sentence(prediction, runs):
        return [build_default_corrected_segment(prediction)], False

    raw_segments = collect_raw_segments_for_sentence(record.raw_segments, prediction.start, prediction.end)
    approximated_texts = approximate_run_texts(prediction.text, runs)
    total_run_duration = sum(max(run["duration_sec"], 0.0) for run in runs) or prediction.duration_sec or 1.0
    assigned_segments: list[CorrectedSegment] = []

    raw_by_run: dict[int, list[dict]] = {}
    for raw in raw_segments:
        run_index = locate_run_index_by_time(runs, raw["midpoint"])
        raw_by_run.setdefault(run_index, []).append(raw)

    for run_index, run in enumerate(runs):
        assigned_raw = raw_by_run.get(run_index, [])
        non_empty_texts = [item["text"] for item in assigned_raw if item["text"]]
        raw_text = "".join(non_empty_texts).strip()
        expected_chars = max(
            1,
            int(round(len(prediction.text.strip()) * (max(run["duration_sec"], 0.0) / total_run_duration))),
        )
        if raw_text and 0.5 * expected_chars <= len(raw_text) <= 1.5 * expected_chars:
            text = raw_text
        else:
            text = approximated_texts[run_index]
        start = float(run["start"])
        end = float(run["end"])
        confidence = min(0.97, max(0.6, 0.54 + 1.6 * run["mean_margin"]))
        assigned_segments.append(
            CorrectedSegment(
                source_sentence_index=prediction.sentence_index,
                segment_index=run_index,
                start=float(start),
                end=float(end),
                duration_sec=float(max(0.0, end - start)),
                text=text,
                predicted_speaker_id=run["speaker"],
                confidence=float(confidence),
                kind="split",
            )
        )

    assigned_segments = [item for item in assigned_segments if item.duration_sec > 0]
    if len(assigned_segments) <= 1:
        return [build_default_corrected_segment(prediction)], False
    return assigned_segments, True


def build_default_corrected_segment(prediction: SentencePrediction) -> CorrectedSegment:
    return CorrectedSegment(
        source_sentence_index=prediction.sentence_index,
        segment_index=0,
        start=prediction.start,
        end=prediction.end,
        duration_sec=prediction.duration_sec,
        text=prediction.text,
        predicted_speaker_id=prediction.predicted_speaker_id,
        confidence=prediction.confidence,
        kind="whole",
    )


def should_split_sentence(prediction: SentencePrediction, runs: list[dict]) -> bool:
    if prediction.duration_sec < MIXED_SENTENCE_MIN_DURATION_SEC:
        return False
    if len(runs) < 2 or len(runs) > MIXED_SENTENCE_MAX_RUNS:
        return False
    if len({run["speaker"] for run in runs}) < 2:
        return False
    if sum(run["window_count"] for run in runs) < MIXED_SENTENCE_MIN_WINDOWS:
        return False
    for run in runs:
        if run["window_count"] < MIXED_SENTENCE_MIN_RUN_WINDOWS:
            return False
        if run["duration_sec"] < MIXED_SENTENCE_MIN_RUN_DURATION_SEC:
            return False
        if run["mean_margin"] < MIXED_SENTENCE_MIN_MARGIN:
            return False
    return True


def collect_raw_segments_for_sentence(raw_segments: list[dict], start: float, end: float) -> list[dict]:
    collected = []
    for raw in raw_segments:
        raw_start = max(float(raw.get("start", 0.0)), start)
        raw_end = min(float(raw.get("end", 0.0)), end)
        if raw_end <= raw_start:
            continue
        collected.append(
            {
                "start": raw_start,
                "end": raw_end,
                "midpoint": (raw_start + raw_end) / 2.0,
                "text": (raw.get("text") or "").strip(),
            }
        )
    collected.sort(key=lambda item: (item["start"], item["end"]))
    return collected


def approximate_run_texts(text: str, runs: list[dict]) -> list[str]:
    normalized = text.strip()
    if not normalized or not runs:
        return [normalized for _ in runs]
    weights = [max(run["duration_sec"], 0.0) for run in runs]
    total_weight = sum(weights) or float(len(runs))
    total_chars = len(normalized)
    boundaries = [0]
    acc = 0.0
    for weight in weights[:-1]:
        acc += weight / total_weight
        boundaries.append(min(total_chars, max(boundaries[-1], int(round(acc * total_chars)))))
    boundaries.append(total_chars)

    slices: list[str] = []
    for start_idx, end_idx in zip(boundaries, boundaries[1:]):
        slices.append(normalized[start_idx:end_idx].strip())
    if slices:
        slices[-1] = normalized[boundaries[-2] :].strip()
    return slices


def locate_run_index_by_time(runs: list[dict], timestamp: float) -> int:
    if not runs:
        return 0
    for idx, run in enumerate(runs):
        if idx == len(runs) - 1:
            if run["start"] <= timestamp <= run["end"]:
                return idx
        elif run["start"] <= timestamp < run["end"]:
            return idx
    distances = [min(abs(timestamp - run["start"]), abs(timestamp - run["end"])) for run in runs]
    return int(np.argmin(distances))


def build_sentence_window_runs(
    sentence_windows: list[WindowMeasurement],
    threshold: float,
    sentence_start: float,
    sentence_end: float,
) -> list[dict]:
    if not sentence_windows:
        return []
    ordered = sorted(sentence_windows, key=lambda item: (item.start, item.end, item.window_index))
    labels = ["host" if item.host_similarity >= threshold else "guest" for item in ordered]
    labels = smooth_window_labels(labels)
    labels = merge_short_window_runs(labels, ordered, threshold)
    runs = compress_window_labels(labels, ordered, threshold)
    if not runs:
        return []

    centers = np.asarray([(item.start + item.end) / 2.0 for item in ordered], dtype=np.float32)
    enriched: list[dict] = []
    for run_index, run in enumerate(runs):
        start_boundary = sentence_start
        end_boundary = sentence_end
        if run_index > 0:
            prev = runs[run_index - 1]
            start_boundary = float((centers[prev["end_idx"]] + centers[run["start_idx"]]) / 2.0)
        if run_index + 1 < len(runs):
            nxt = runs[run_index + 1]
            end_boundary = float((centers[run["end_idx"]] + centers[nxt["start_idx"]]) / 2.0)
        enriched.append(
            {
                "speaker": run["speaker"],
                "start": float(max(sentence_start, start_boundary)),
                "end": float(min(sentence_end, end_boundary)),
                "duration_sec": float(max(0.0, min(sentence_end, end_boundary) - max(sentence_start, start_boundary))),
                "window_count": run["window_count"],
                "mean_host_similarity": run["mean_host_similarity"],
                "mean_margin": run["mean_margin"],
            }
        )
    return [run for run in enriched if run["duration_sec"] > 0]


def smooth_window_labels(labels: list[str]) -> list[str]:
    smoothed = list(labels)
    if len(smoothed) < 3:
        return smoothed
    for _ in range(MIXED_SENTENCE_SMOOTHING_PASSES):
        updated = list(smoothed)
        for idx in range(1, len(smoothed) - 1):
            if smoothed[idx - 1] == smoothed[idx + 1] != smoothed[idx]:
                updated[idx] = smoothed[idx - 1]
        smoothed = updated
    return smoothed


def merge_short_window_runs(
    labels: list[str],
    windows: list[WindowMeasurement],
    threshold: float,
) -> list[str]:
    merged = list(labels)
    while True:
        runs = compress_window_labels(merged, windows, threshold)
        if len(runs) <= 1:
            return merged
        target_run = None
        for run_index, run in enumerate(runs):
            if (
                run["window_count"] < MIXED_SENTENCE_MIN_RUN_WINDOWS
                or run["duration_sec"] < MIXED_SENTENCE_MIN_RUN_DURATION_SEC
                or run["mean_margin"] < MIXED_SENTENCE_MIN_MARGIN
            ):
                target_run = (run_index, run)
                break
        if target_run is None:
            return merged

        run_index, run = target_run
        previous = runs[run_index - 1] if run_index > 0 else None
        following = runs[run_index + 1] if run_index + 1 < len(runs) else None
        if previous is not None and following is not None and previous["speaker"] == following["speaker"]:
            replacement = previous["speaker"]
        elif previous is None and following is not None:
            replacement = following["speaker"]
        elif following is None and previous is not None:
            replacement = previous["speaker"]
        elif previous is not None and following is not None:
            replacement = (
                previous["speaker"]
                if previous["window_count"] >= following["window_count"]
                else following["speaker"]
            )
        else:
            return merged
        for idx in range(run["start_idx"], run["end_idx"] + 1):
            merged[idx] = replacement


def compress_window_labels(
    labels: list[str],
    windows: list[WindowMeasurement],
    threshold: float,
) -> list[dict]:
    if not labels:
        return []
    runs: list[dict] = []
    start_idx = 0
    current = labels[0]
    for idx in range(1, len(labels) + 1):
        if idx < len(labels) and labels[idx] == current:
            continue
        segment_windows = windows[start_idx:idx]
        similarities = [item.host_similarity for item in segment_windows]
        run_start = segment_windows[0].start
        run_end = segment_windows[-1].end
        runs.append(
            {
                "speaker": current,
                "start_idx": start_idx,
                "end_idx": idx - 1,
                "window_count": len(segment_windows),
                "duration_sec": float(max(0.0, run_end - run_start)),
                "mean_host_similarity": float(np.mean(similarities)),
                "mean_margin": float(np.mean([abs(value - threshold) for value in similarities])),
            }
        )
        if idx < len(labels):
            start_idx = idx
            current = labels[idx]
    return runs


def collect_window_measurements(
    record: PartRecord,
    measurements: list[SegmentMeasurement],
    backend: EmbeddingBackend,
    host_centroid: np.ndarray,
    embedding_cache: EmbeddingCache | None = None,
    audio_context: AudioContext | None = None,
) -> list[WindowMeasurement]:
    windows: list[WindowMeasurement] = []
    for measurement in measurements:
        sentence = record.sentences[measurement.sentence_index]
        for window_index, (start, end) in enumerate(iter_window_ranges(measurement.start, measurement.end)):
            vector, duration_sec, _ = extract_segment_features(
                audio_path=record.audio_path,
                segment_key=measurement.sentence_index * 10_000 + window_index,
                start=start,
                end=end,
                text=f"{sentence.get('text', '')}__window_{window_index}",
                backend=backend,
                embedding_cache=embedding_cache,
                audio_context=audio_context,
            )
            windows.append(
                WindowMeasurement(
                    sentence_index=measurement.sentence_index,
                    window_index=window_index,
                    start=start,
                    end=end,
                    duration_sec=duration_sec,
                    vector=vector,
                    host_similarity=cosine_similarity(vector, host_centroid),
                )
            )
    return windows


def iter_window_ranges(start: float, end: float) -> list[tuple[float, float]]:
    duration = max(0.0, end - start)
    if duration < WINDOW_REFINE_MIN_WINDOW_SEC:
        return []
    if duration <= WINDOW_REFINE_WINDOW_SEC:
        return [(start, end)]

    windows: list[tuple[float, float]] = []
    cursor = start
    while cursor < end:
        right = min(cursor + WINDOW_REFINE_WINDOW_SEC, end)
        if right - cursor >= WINDOW_REFINE_MIN_WINDOW_SEC:
            windows.append((cursor, right))
        if right >= end:
            break
        cursor += WINDOW_REFINE_HOP_SEC
    if windows and windows[-1][1] < end and end - windows[-1][1] >= WINDOW_REFINE_MIN_WINDOW_SEC:
        windows.append((max(start, end - WINDOW_REFINE_WINDOW_SEC), end))
    return windows


def apply_overlap_confidence_adjustment(
    predictions: list[SentencePrediction],
) -> list[SentencePrediction]:
    adjusted: list[SentencePrediction] = []
    for item in predictions:
        if not item.overlap_suspected:
            adjusted.append(item)
            continue
        confidence = min(item.confidence * OVERLAP_CONFIDENCE_SCALE, OVERLAP_CONFIDENCE_CAP)
        adjusted.append(replace(item, confidence=confidence))
    return adjusted


def apply_opening_host_prior(predictions: list[SentencePrediction]) -> list[SentencePrediction]:
    if not predictions:
        return predictions
    adjusted = list(predictions)
    opening_anchor = adjusted[0].start
    limit = min(len(adjusted), OPENING_HOST_MAX_SENTENCES)
    for idx in range(limit):
        item = adjusted[idx]
        if item.start - opening_anchor > OPENING_HOST_WINDOW_SEC:
            break
        if item.predicted_speaker_id == "host":
            continue
        if not looks_like_opening_host_prompt(item.text):
            continue
        if not has_guest_followup(adjusted, idx):
            continue
        adjusted[idx] = replace(
            item,
            predicted_speaker_id="host",
            confidence=max(0.66, min(item.confidence, 0.78)),
        )
    return adjusted


def smooth_edge_predictions(predictions: list[SentencePrediction]) -> list[SentencePrediction]:
    if len(predictions) < 2:
        return predictions
    adjusted = list(predictions)
    first_target = consensus_speaker(adjusted[1:3])
    if should_flip_edge(adjusted[0], first_target):
        adjusted[0] = replace(
            adjusted[0],
            predicted_speaker_id=first_target,
            confidence=max(adjusted[0].confidence, 0.6),
        )

    last_target = consensus_speaker(adjusted[max(0, len(adjusted) - 3) : len(adjusted) - 1])
    if should_flip_edge(adjusted[-1], last_target):
        adjusted[-1] = replace(
            adjusted[-1],
            predicted_speaker_id=last_target,
            confidence=max(adjusted[-1].confidence, 0.6),
        )
    return adjusted


def normalize_text(text: str) -> str:
    return text.lower().translate(TEXT_TRANSLATION)


def looks_like_opening_host_prompt(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    has_prompt = any(cue in normalized for cue in HOST_PROMPT_CUES)
    has_greeting = any(normalized.startswith(prefix) for prefix in HOST_GREETING_PREFIXES)
    return has_prompt and (has_greeting or len(normalized) <= 12)


def has_guest_followup(predictions: list[SentencePrediction], idx: int) -> bool:
    for follow in predictions[idx + 1 : idx + 3]:
        if follow.predicted_speaker_id == "guest" and follow.duration_sec >= 1.5:
            return True
    return False


def consensus_speaker(items: list[SentencePrediction]) -> str | None:
    if len(items) < 2:
        return None
    speakers = {item.predicted_speaker_id for item in items}
    if len(speakers) == 1:
        return next(iter(speakers))
    return None


def should_flip_edge(item: SentencePrediction, target: str | None) -> bool:
    if target is None or target == item.predicted_speaker_id:
        return False
    normalized = normalize_text(item.text)
    if not normalized:
        return False
    if item.duration_sec > EDGE_SHORT_UTTERANCE_SEC and item.confidence > EDGE_LOW_CONFIDENCE:
        return False
    return len(normalized) <= 8 or item.confidence <= EDGE_LOW_CONFIDENCE or not item.feature_usable
