#!/usr/bin/env python3
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path('/home/duino/ws/ququ/process_youtube')
SRC_MP3 = BASE / 'data/01_downloads/曲曲2025（全）/56 - 曲曲現場直播 2025年8月8日 ｜ 曲曲麥肯錫.mp3'
OUT_DIR = BASE / 'data/03_transcripts/曲曲2025（全）/56 - 曲曲現場直播 2025年8月8日 ｜ 曲曲麥肯錫_processed'
MANIFEST = OUT_DIR / '_section_manifest.raw.json'
REPORT = OUT_DIR / '_audio_check_report.json'

assert SRC_MP3.exists(), SRC_MP3
assert MANIFEST.exists(), MANIFEST

manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
sections = sorted(manifest['sections'], key=lambda x: x['index'])

ffmpeg_bin = 'ffmpeg'
vol_re = re.compile(r'mean_volume:\s*([\-\d\.]+) dB.*?max_volume:\s*([\-\d\.]+) dB', re.S)

def measure_sentence(section: dict, sent: dict) -> dict:
    start = float(sent['start'])
    end = float(sent['end'])
    dur = max(0.02, end - start)
    cmd = [
        ffmpeg_bin,
        '-hide_banner','-nostats',
        '-ss', f'{start:.2f}',
        '-t', f'{dur:.2f}',
        '-i', str(SRC_MP3),
        '-af', 'volumedetect',
        '-f', 'null','-'
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        text = proc.stderr
        m = vol_re.search(text)
        mean_vol = float(m.group(1)) if m else None
        max_vol = float(m.group(2)) if m else None
    except Exception:
        mean_vol = max_vol = None
    return {
        'speaker_id': sent['speaker_id'],
        'start': round(start, 2),
        'end': round(end, 2),
        'duration': round(dur, 2),
        'mean_vol_db': mean_vol,
        'max_vol_db': max_vol,
    }

def process_section(section: dict) -> dict:
    title = section['title']
    path = OUT_DIR / f"{title}.json"
    if not path.exists():
        return {'title': title, 'ok': False, 'error': 'formal json missing'}
    obj = json.loads(path.read_text(encoding='utf-8'))
    sentences = obj.get('sentences', [])
    n = len(sentences)
    idxs = list(range(n))
    if n > 30:
        step = max(1, n // 30)
        idxs = list(range(0, n, step))[:30]
    feats = [measure_sentence(section, sentences[i]) for i in idxs]
    host_vals = [f['mean_vol_db'] for f in feats if f['speaker_id'] == 'host' and f['mean_vol_db'] is not None]
    guest_vals = [f['mean_vol_db'] for f in feats if f['speaker_id'] == 'guest' and f['mean_vol_db'] is not None]
    agg = {
        'title': title,
        'index': int(section['index']),
        'kind': section['kind'],
        'count_host': len(host_vals),
        'count_guest': len(guest_vals),
        'mean_vol_host': (sum(host_vals)/len(host_vals)) if host_vals else None,
        'mean_vol_guest': (sum(guest_vals)/len(guest_vals)) if guest_vals else None,
        'feats': feats,
    }
    if section['kind'] == 'call' and agg['count_guest'] == 0:
        agg['suspect'] = 'no_guest_samples'
    else:
        agg['suspect'] = None
    return {'title': title, 'ok': True, 'agg': agg}

results = []
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = [ex.submit(process_section, sec) for sec in sections]
    for fut in as_completed(futs):
        results.append(fut.result())

results.sort(key=lambda x: x.get('agg', {}).get('index', 9999))
REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('written', REPORT)
