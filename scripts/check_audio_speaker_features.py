#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

import numpy as np


@dataclass
class ClipFeature:
    file: str
    speaker_id: str
    start: float
    end: float
    text: str
    vector: np.ndarray


def extract_wav_samples(audio_path: Path, start: float, duration: float, sr: int = 16000) -> tuple[np.ndarray, int]:
    duration = max(0.4, duration)
    with tempfile.NamedTemporaryFile(suffix='.wav') as tmp:
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-ss', f'{start:.3f}', '-t', f'{duration:.3f}', '-i', str(audio_path),
            '-ac', '1', '-ar', str(sr), '-f', 'wav', tmp.name, '-y'
        ]
        subprocess.run(cmd, check=True)
        with wave.open(tmp.name, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            return data, wf.getframerate()


def feature_from_audio(samples: np.ndarray, sr: int) -> np.ndarray:
    if len(samples) < sr // 2:
        pad = np.zeros(sr // 2 - len(samples), dtype=np.float32)
        samples = np.concatenate([samples, pad])

    samples = samples - np.mean(samples)
    rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-8)
    if rms > 0:
        samples = samples / (rms * 4)

    frame_len = 1024
    hop = 512
    if len(samples) < frame_len:
        samples = np.pad(samples, (0, frame_len - len(samples)))

    window = np.hanning(frame_len)
    spectra = []
    zcrs = []
    rmss = []
    for i in range(0, len(samples) - frame_len + 1, hop):
        frame = samples[i:i+frame_len]
        rmss.append(float(np.sqrt(np.mean(frame ** 2))))
        zcrs.append(float(np.mean(np.abs(np.diff(np.signbit(frame)).astype(np.float32)))))
        mag = np.abs(np.fft.rfft(frame * window)) + 1e-8
        spectra.append(mag)

    spec = np.mean(np.stack(spectra), axis=0)
    freqs = np.fft.rfftfreq(frame_len, d=1/sr)
    spec_sum = float(np.sum(spec))
    centroid = float(np.sum(freqs * spec) / spec_sum)
    bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * spec) / spec_sum))
    cum = np.cumsum(spec)
    rolloff_idx = int(np.searchsorted(cum, cum[-1] * 0.85))
    rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])

    def band_energy(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return float(np.sum(spec[mask]) / spec_sum)

    low = band_energy(0, 300)
    low_mid = band_energy(300, 1200)
    mid = band_energy(1200, 3000)
    high = band_energy(3000, 7000)
    feats = np.array([
        centroid, bandwidth, rolloff,
        low, low_mid, mid, high,
        float(np.mean(zcrs)), float(np.std(zcrs)),
        float(np.mean(rmss)), float(np.std(rmss)),
    ], dtype=np.float32)
    return feats


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - float(np.dot(a, b) / (na * nb))


def select_sentences(sentences: List[Dict[str, Any]], speaker_id: str, limit: int = 6) -> List[Dict[str, Any]]:
    chosen = []
    for s in sentences:
        dur = s['end'] - s['start']
        txt = s['text'].strip()
        if s['speaker_id'] == speaker_id and dur >= 1.2 and len(txt) >= 6:
            chosen.append(s)
        if len(chosen) >= limit:
            break
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--audio', required=True)
    ap.add_argument('--dir', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    audio_path = Path(args.audio)
    out_dir = Path(args.dir)
    out_path = Path(args.out)

    opening = json.loads((out_dir / '00_开场.json').read_text())
    host_refs = select_sentences(opening['sentences'], 'host', limit=8)
    host_features = []
    for s in host_refs:
        data, sr = extract_wav_samples(audio_path, s['start'], min(4.0, s['end'] - s['start']))
        host_features.append(feature_from_audio(data, sr))
    host_ref = np.mean(np.stack(host_features), axis=0)

    report = {
        'audio_file': str(audio_path),
        'host_reference_sentences': len(host_refs),
        'calls': []
    }

    for p in sorted(out_dir.glob('*_连麦.json')):
        obj = json.loads(p.read_text())
        sentences = obj['sentences']
        host_sents = select_sentences(sentences, 'host', limit=6)
        guest_sents = select_sentences(sentences, 'guest', limit=6)
        host_dists = []
        guest_dists = []
        examples = {'host': [], 'guest': []}
        for label, selected, bucket in [('host', host_sents, host_dists), ('guest', guest_sents, guest_dists)]:
            for s in selected:
                data, sr = extract_wav_samples(audio_path, s['start'], min(4.0, s['end'] - s['start']))
                feat = feature_from_audio(data, sr)
                dist = cosine_distance(feat, host_ref)
                bucket.append(dist)
                examples[label].append({
                    'start': s['start'],
                    'end': s['end'],
                    'distance_to_host_ref': round(dist, 6),
                    'text': s['text'][:60]
                })
        host_mean = float(np.mean(host_dists)) if host_dists else None
        guest_mean = float(np.mean(guest_dists)) if guest_dists else None
        report['calls'].append({
            'file': p.name,
            'persona': obj['meta']['persona'],
            'host_mean_distance_to_host_ref': host_mean,
            'guest_mean_distance_to_host_ref': guest_mean,
            'delta_guest_minus_host': None if host_mean is None or guest_mean is None else guest_mean - host_mean,
            'sample_counts': {'host': len(host_dists), 'guest': len(guest_dists)},
            'examples': examples,
        })

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'wrote report to {out_path}')
    for item in report['calls']:
        print(item['file'], 'host=', item['host_mean_distance_to_host_ref'], 'guest=', item['guest_mean_distance_to_host_ref'], 'delta=', item['delta_guest_minus_host'])


if __name__ == '__main__':
    main()
