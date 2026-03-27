#!/usr/bin/env python3
from __future__ import annotations
import json
import librosa, numpy as np
from pathlib import Path

BASE = Path('/home/duino/ws/ququ/process_youtube')
AUDIO_DIR = BASE / 'data/02_audio_splits/曲曲2025（全）'
SESSION = '73 - 曲曲現場直播 2025年10月16日 ｜ 曲曲麥肯錫'
AUDIO_FILES = [
    AUDIO_DIR / f'{SESSION}_part01.mp3',
    AUDIO_DIR / f'{SESSION}_part02.mp3',
    AUDIO_DIR / f'{SESSION}_part03.mp3',
]
SECTIONS_DIR = BASE / f'data/03_transcripts/曲曲2025（全）/{SESSION}_processed'
OUT = BASE / f'data/03_transcripts/曲曲2025（全）/{SESSION}_processed/_speaker_spectra_check.json'

# Simple spectral centroid + MFCC signature per sentence, compare host vs guest clusters

def load_audio(fp: Path):
    y, sr = librosa.load(str(fp), sr=None, mono=True)
    return y, sr


def ts_to_part_offset(ts: float):
    # parts ~ 0-~4800s, 4800-~9600s, 9600-~14400s
    if ts < 4800:
        return 0, ts
    elif ts < 9600:
        return 1, ts - 4800
    else:
        return 2, ts - 9600


def sentence_signature(y: np.ndarray, sr: int, st: float, ed: float):
    s = int(st * sr)
    e = int(ed * sr)
    s = max(0, min(len(y)-1, s))
    e = max(s+1, min(len(y), e))
    seg = y[s:e]
    if len(seg) < sr*0.3:
        # too short, pad context
        e = min(len(y), e + int(sr*0.2))
        seg = y[s:e]
    if len(seg) < sr*0.2:
        return None
    # features
    sc = librosa.feature.spectral_centroid(y=seg, sr=sr).mean()
    mfcc = librosa.feature.mfcc(y=seg, sr=sr, n_mfcc=13).mean(axis=1)
    return float(sc), [float(x) for x in mfcc]


def main():
    parts = [load_audio(fp) for fp in AUDIO_FILES]
    reports = []
    for sec_fp in sorted(SECTIONS_DIR.glob('*.json')):
        if sec_fp.name.startswith('_'): continue
        obj = json.loads(sec_fp.read_text(encoding='utf-8'))
        meta = obj['meta']
        sentences = obj['sentences']
        kind = meta['kind']
        # only check call segments (host+guest)
        if kind != 'call':
            continue
        sigs = []
        for i, s in enumerate(sentences):
            st = float(s['start']); ed = float(s['end'])
            pidx, off = ts_to_part_offset(st)
            y, sr = parts[pidx]
            sig = sentence_signature(y, sr, off, off + (ed - st))
            if sig is None:
                continue
            sigs.append({'i': i, 'speaker_id': s['speaker_id'], 'sc': sig[0], 'mfcc': sig[1], 'dur': ed - st})
        if not sigs:
            continue
        # cluster by speaker
        host = np.array([x['mfcc'] for x in sigs if x['speaker_id']=='host'])
        guest = np.array([x['mfcc'] for x in sigs if x['speaker_id']=='guest'])
        if len(host) < 3 or len(guest) < 3:
            continue
        host_centroid = host.mean(axis=0)
        guest_centroid = guest.mean(axis=0)
        # compute assignments and mark mismatches where distance to opposite centroid is smaller
        def dist(a, b):
            return float(np.linalg.norm(a-b))
        mismatches = []
        for x in sigs:
            v = np.array(x['mfcc'])
            dh = dist(v, host_centroid)
            dg = dist(v, guest_centroid)
            predicted = 'host' if dh < dg else 'guest'
            if predicted != x['speaker_id'] and x['dur'] >= 1.0:
                mismatches.append({'sentence_index': x['i'], 'label': x['speaker_id'], 'pred': predicted, 'dh': dh, 'dg': dg})
        reports.append({'file': sec_fp.name, 'mismatches': mismatches, 'host_n': len(host), 'guest_n': len(guest)})
    OUT.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('written', OUT)

if __name__ == '__main__':
    main()
