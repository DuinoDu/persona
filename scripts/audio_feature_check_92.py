#!/usr/bin/env python3
import json, subprocess, tempfile, os, wave, contextlib, math
from pathlib import Path

BASE = Path('/home/duino/ws/ququ/process_youtube')
MANIFEST = BASE/ 'data/03_transcripts/曲曲2025（全）/92 - 曲曲現場直播 2025年12月19日 ｜ 曲曲麥肯錫_processed/_section_manifest.raw.json'
PARTS = [
  (0.0, 7200.0, BASE/'data/02_audio_splits/曲曲2025（全）/92 - 曲曲現場直播 2025年12月19日 ｜ 曲曲麥肯錫_part01.mp3'),
  (7200.0, 14400.0, BASE/'data/02_audio_splits/曲曲2025（全）/92 - 曲曲現場直播 2025年12月19日 ｜ 曲曲麥肯錫_part02.mp3'),
  (14400.0, 14955.3, BASE/'data/02_audio_splits/曲曲2025（全）/92 - 曲曲現場直播 2025年12月19日 ｜ 曲曲麥肯錫_part03.mp3'),
]

# Helper: map absolute [start,end] to (mp3_path, local_start, duration)
def map_interval(start: float, end: float):
  for p_start, p_end, path in PARTS:
    if start >= p_start and end <= p_end:
      return path, max(0.0, start - p_start), max(0.0, end - start)
  # handle cross-boundary (rare) — clip to part bounds
  for p_start, p_end, path in PARTS:
    if start < p_end and end > p_start:
      ls = max(0.0, start - p_start)
      le = min(end, p_end) - max(start, p_start)
      return path, ls, le
  raise ValueError('interval not mapped')

# Extract short wav via ffmpeg and compute simple spectral features
# Returns (rms_mean, rms_std, zcr_mean)
def analyze_interval(mp3_path: Path, local_start: float, duration: float):
  with tempfile.TemporaryDirectory() as td:
    wav = Path(td)/'seg.wav'
    cmd = [
      'ffmpeg','-v','error','-ss',f'{local_start:.2f}','-t',f'{duration:.2f}',
      '-i',str(mp3_path),'-ar','16000','-ac','1','-f','wav',str(wav)
    ]
    subprocess.check_call(cmd)
    with contextlib.closing(wave.open(str(wav),'rb')) as wf:
      n_channels = wf.getnchannels()
      sr = wf.getframerate()
      n_frames = wf.getnframes()
      frames = wf.readframes(n_frames)
    # Convert to integers
    import numpy as np
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    # Normalize
    data /= 32768.0
    # Frame-wise RMS and ZCR
    frame_len = int(sr * 0.02)  # 20ms
    hop = frame_len
    rms = []
    zcr = []
    for i in range(0, len(data)-frame_len, hop):
      x = data[i:i+frame_len]
      rms.append(math.sqrt((x*x).mean()+1e-12))
      zcr.append(((x[:-1]*x[1:])<0).mean())
    rms = np.array(rms)
    zcr = np.array(zcr)
    return float(rms.mean()), float(rms.std()), float(zcr.mean())

# Load manifest comments
man = json.loads(MANIFEST.read_text(encoding='utf-8'))
comments = [s for s in man['sections'] if s['kind']=='comment']

report = []
for s in comments:
  start = float(s['start'])
  end = float(s['end'])
  dur = end - start
  # skip extremely short comments (< 3s)
  if dur < 3.0:
    continue
  mp3_path, local_start, d = map_interval(start, end)
  try:
    rms_m, rms_std, zcr_m = analyze_interval(mp3_path, local_start, d)
    # Heuristic: monologue tends to have lower variance of RMS and ZCR
    mono_like = (rms_std < 0.05) and (zcr_m < 0.08)
    report.append({
      'file': s['file'],
      'start': start,'end': end,'duration': dur,
      'mp3': str(mp3_path),'local_start': local_start,'local_duration': d,
      'rms_mean': rms_m,'rms_std': rms_std,'zcr_mean': zcr_m,
      'mono_like': mono_like
    })
  except Exception as e:
    report.append({'file': s['file'],'error': str(e)})

out = BASE/ 'data/03_transcripts/曲曲2025（全）/92 - 曲曲現場直播 2025年12月19日 ｜ 曲曲麥肯錫_processed/_audio_feature_report.json'
out.write_text(json.dumps({'comments_checked': report}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Wrote', out)
