from __future__ import annotations

import librosa
import numpy as np

from .config import SAMPLE_RATE


def load_audio_range(audio_path, start: float, end: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    duration = max(0.0, float(end) - float(start))
    if duration <= 0:
        return np.zeros(1, dtype=np.float32)
    waveform, _ = librosa.load(
        str(audio_path),
        sr=sr,
        mono=True,
        offset=max(0.0, float(start)),
        duration=duration,
    )
    if waveform.size == 0:
        return np.zeros(1, dtype=np.float32)
    return waveform.astype(np.float32)


def load_audio_slice(
    audio_path,
    start: float,
    end: float,
    sr: int = SAMPLE_RATE,
    preloaded_waveform: np.ndarray | None = None,
    preloaded_start: float = 0.0,
) -> np.ndarray:
    duration = max(0.0, float(end) - float(start))
    if duration <= 0:
        return np.zeros(1, dtype=np.float32)
    if preloaded_waveform is not None:
        if preloaded_waveform.size == 0:
            return np.zeros(1, dtype=np.float32)
        relative_start = max(0.0, float(start) - float(preloaded_start))
        relative_end = max(relative_start, float(end) - float(preloaded_start))
        sample_start = max(0, int(round(relative_start * sr)))
        sample_end = max(sample_start, int(round(relative_end * sr)))
        waveform = preloaded_waveform[sample_start:sample_end]
        if waveform.size == 0:
            return np.zeros(1, dtype=np.float32)
        return waveform.astype(np.float32, copy=False)
    return load_audio_range(audio_path, start, end, sr)


def _summary_stats(matrix: np.ndarray) -> np.ndarray:
    return np.concatenate([matrix.mean(axis=1), matrix.std(axis=1)])


def spectrum_embedding(waveform: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    if waveform.size < sr // 4:
        waveform = np.pad(waveform, (0, max(0, sr // 4 - waveform.size)))

    if np.max(np.abs(waveform)) > 0:
        waveform = waveform / np.max(np.abs(waveform))

    mfcc = librosa.feature.mfcc(y=waveform, sr=sr, n_mfcc=20)
    if mfcc.shape[1] < 3:
        delta = np.zeros_like(mfcc)
    else:
        width = min(9, mfcc.shape[1] if mfcc.shape[1] % 2 == 1 else mfcc.shape[1] - 1)
        delta = librosa.feature.delta(mfcc, width=width, mode="nearest")
    mel = librosa.power_to_db(librosa.feature.melspectrogram(y=waveform, sr=sr, n_mels=40), ref=np.max)
    contrast = librosa.feature.spectral_contrast(y=waveform, sr=sr)
    centroid = librosa.feature.spectral_centroid(y=waveform, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(y=waveform, sr=sr)
    rolloff = librosa.feature.spectral_rolloff(y=waveform, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y=waveform)
    rms = librosa.feature.rms(y=waveform)

    vector = np.concatenate(
        [
            _summary_stats(mfcc),
            _summary_stats(delta),
            _summary_stats(mel),
            _summary_stats(contrast),
            _summary_stats(centroid),
            _summary_stats(bandwidth),
            _summary_stats(rolloff),
            _summary_stats(zcr),
            _summary_stats(rms),
        ]
    ).astype(np.float32)

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm

    return vector


def waveform_rms(waveform: np.ndarray) -> float:
    if waveform.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(waveform, dtype=np.float32))))


def cosine_similarity(lhs: np.ndarray, rhs: np.ndarray) -> float:
    lhs_norm = np.linalg.norm(lhs)
    rhs_norm = np.linalg.norm(rhs)
    if lhs_norm == 0 or rhs_norm == 0:
        return 0.0
    return float(np.dot(lhs, rhs) / (lhs_norm * rhs_norm))
