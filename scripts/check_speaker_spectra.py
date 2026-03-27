#!/usr/bin/env python3
import argparse, json, math, subprocess, sys
from pathlib import Path
import numpy as np


def extract_pcm(mp3_path: str, start: float, end: float, sr: int = 16000) -> np.ndarray:
    duration = max(0.05, end - start)
    cmd = [
        'ffmpeg', '-v', 'error', '-ss', str(start), '-t', str(duration), '-i', mp3_path,
        '-ac', '1', '-ar', str(sr), '-f', 's16le', '-'
    ]
    raw = subprocess.check_output(cmd)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def frame_logspec(audio: np.ndarray, sr: int = 16000, n_fft: int = 1024, hop: int = 256) -> np.ndarray:
    if len(audio) < n_fft:
        audio = np.pad(audio, (0, n_fft - len(audio)))
    window = np.hanning(n_fft).astype(np.float32)
    frames = []
    for i in range(0, max(1, len(audio) - n_fft + 1), hop):
        x = audio[i:i+n_fft]
        if len(x) < n_fft:
            x = np.pad(x, (0, n_fft - len(x)))
        spec = np.fft.rfft(x * window)
        mag = np.abs(spec) + 1e-8
        frames.append(np.log(mag))
    return np.stack(frames, axis=0)


def embedding(audio: np.ndarray) -> np.ndarray:
    logspec = frame_logspec(audio)
    emb = logspec.mean(axis=0)
    emb = emb - emb.mean()
    norm = np.linalg.norm(emb)
    if norm == 0:
        return emb
    return emb / norm


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def spectral_stats(audio: np.ndarray, sr: int = 16000):
    if len(audio) == 0:
        return {}
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    freqs = np.fft.rfftfreq(len(audio), d=1.0/sr)
    power = spec**2 + 1e-12
    centroid = float((freqs * power).sum() / power.sum())
    cum = np.cumsum(power)
    rolloff = float(freqs[np.searchsorted(cum, 0.85 * cum[-1])])
    zcr = float(((audio[:-1] * audio[1:]) < 0).mean()) if len(audio) > 1 else 0.0
    rms = float(np.sqrt(np.mean(audio**2)))
    return {'centroid_hz': round(centroid, 1), 'rolloff_hz': round(rolloff, 1), 'zcr': round(zcr, 4), 'rms': round(rms, 4)}


def load_sentence(path: Path, idx: int):
    obj = json.loads(path.read_text())
    row = obj['sentences'][idx]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audio', required=True)
    ap.add_argument('--host-json', required=True)
    ap.add_argument('--host-idx', type=int, required=True)
    ap.add_argument('--guest-json', required=True)
    ap.add_argument('--guest-idx', type=int, required=True)
    ap.add_argument('--check', nargs='+', required=True, help='json_path:idx ...')
    args = ap.parse_args()

    host_row = load_sentence(Path(args.host_json), args.host_idx)
    guest_row = load_sentence(Path(args.guest_json), args.guest_idx)
    host_audio = extract_pcm(args.audio, host_row['start'], host_row['end'])
    guest_audio = extract_pcm(args.audio, guest_row['start'], guest_row['end'])
    host_emb = embedding(host_audio)
    guest_emb = embedding(guest_audio)

    print('HOST_REF', Path(args.host_json).name, args.host_idx, host_row['speaker_id'], host_row['start'], host_row['end'], spectral_stats(host_audio))
    print('GUEST_REF', Path(args.guest_json).name, args.guest_idx, guest_row['speaker_id'], guest_row['start'], guest_row['end'], spectral_stats(guest_audio))

    for item in args.check:
        jpath, sidx = item.rsplit(':', 1)
        row = load_sentence(Path(jpath), int(sidx))
        audio = extract_pcm(args.audio, row['start'], row['end'])
        emb = embedding(audio)
        hs = cosine(emb, host_emb)
        gs = cosine(emb, guest_emb)
        stats = spectral_stats(audio)
        inferred = 'host_like' if hs >= gs else 'guest_like'
        print('CHECK', Path(jpath).name, sidx, row['speaker_id'], row['start'], row['end'], f'host_sim={hs:.4f}', f'guest_sim={gs:.4f}', inferred, stats, row['text'][:80])

if __name__ == '__main__':
    main()
