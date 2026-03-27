#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
YEAR_ROOT = TRANSCRIPTS_ROOT / '曲曲2023（全）'
RECORDS = ROOT / 'data/04_check_v1/2023_records.jsonl'
BACKUP_ROOT = TRANSCRIPTS_ROOT / '_qc_fix_backups/曲曲2023_20260326_safe'
ARTIFACT_ROOT = TRANSCRIPTS_ROOT / '_qc_fix_backups/曲曲2023_artifacts_20260326'
HOST_NAME = '曲曲'
GUEST_NAME = '嘉宾'


ARTIFACT_PATTERNS = ['__retry_backup_', '（若不存在则创建）']


def ts(seconds: float) -> str:
    total = round(max(0.0, float(seconds)), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f'{hours:02d}:{minutes:02d}:{secs:05.2f}'


def parse_ts(value: str) -> float:
    h, m, s = value.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def backup(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    dst = BACKUP_ROOT / path.relative_to(ROOT)
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def backup_dir_move(path: Path) -> Path:
    rel = path.relative_to(TRANSCRIPTS_ROOT)
    dst = ARTIFACT_ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst


def load_records() -> list[dict[str, Any]]:
    out = []
    for line in RECORDS.read_text(encoding='utf-8').splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def infer_index(path: Path, meta: dict[str, Any] | None = None) -> int:
    meta = meta or {}
    if isinstance(meta.get('index'), int):
        return meta['index']
    m = re.match(r'^(\d+)', path.stem)
    return int(m.group(1)) if m else 0


def infer_kind(path: Path, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    kind = meta.get('kind')
    if kind in {'opening', 'call', 'comment'}:
        return kind
    stem = path.stem
    if '开场' in stem:
        return 'opening'
    if '连麦' in stem:
        return 'call'
    return 'comment'


def infer_persona(path: Path, kind: str, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    persona = meta.get('persona')
    if isinstance(persona, str) and persona.strip():
        return persona.strip()
    stem = path.stem
    stem = re.sub(r'^(\d+_)?', '', stem)
    stem = re.sub(r'_(连麦|评论)$', '', stem)
    if kind == 'opening':
        return '开场'
    return stem.strip()


def infer_title(path: Path, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    title = meta.get('title')
    if isinstance(title, str) and title.strip():
        return title.strip()
    return path.stem


def normalize_source_file(meta: dict[str, Any] | None, fallback: str) -> str:
    meta = meta or {}
    src = meta.get('source_file')
    if isinstance(src, str) and src.strip():
        return Path(src).name
    return fallback


def expected_speaker_meta(kind: str) -> tuple[list[str], dict[str, str]]:
    if kind == 'call':
        return ['host', 'guest'], {'host': HOST_NAME, 'guest': GUEST_NAME}
    return ['host'], {'host': HOST_NAME}


def normalize_speaker_id(kind: str, raw_id: Any, raw_name: Any) -> str:
    sid = '' if raw_id is None else str(raw_id)
    sname = '' if raw_name is None else str(raw_name)
    if sid in {'host', 'guest'}:
        return sid if kind == 'call' else 'host'
    if '曲曲' in sname or '主播' in sname:
        return 'host'
    if '嘉宾' in sname or '观众' in sname:
        return 'guest' if kind == 'call' else 'host'
    sid_low = sid.lower()
    if 'host' in sid_low:
        return 'host'
    if 'guest' in sid_low:
        return 'guest' if kind == 'call' else 'host'
    if sid.startswith('SPEAKER_') or sid == 'UNKNOWN' or sid == 'unknown':
        return 'guest' if kind == 'call' else 'host'
    return 'guest' if kind == 'call' else 'host'


def normalize_loaded_obj(path: Path, obj: dict[str, Any], note_suffix: str) -> dict[str, Any]:
    meta = obj.get('meta', {}) if isinstance(obj, dict) else {}
    sentences = obj.get('sentences', []) if isinstance(obj, dict) else []
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(sentences, list):
        sentences = []

    kind = infer_kind(path, meta)
    source_file = normalize_source_file(meta, path.parent.name.removesuffix('_processed') + '.json')
    cleaned = []
    for s in sentences:
        if not isinstance(s, dict):
            continue
        text = '' if s.get('text') is None else str(s.get('text'))
        if not text.strip():
            continue
        start = round(max(0.0, float(s.get('start', 0.0) or 0.0)), 2)
        end = round(max(start, float(s.get('end', start) or start)), 2)
        sid = normalize_speaker_id(kind, s.get('speaker_id'), s.get('speaker_name'))
        if kind != 'call':
            sid = 'host'
        cleaned.append({
            'speaker_id': sid,
            'speaker_name': HOST_NAME if sid == 'host' else GUEST_NAME,
            'start': start,
            'end': end,
            'text': text,
        })
    cleaned.sort(key=lambda x: (x['start'], x['end'], x['speaker_id']))

    start = round(min([float(meta.get('start', 0.0) or 0.0)] + [s['start'] for s in cleaned]), 2) if cleaned else round(max(0.0, float(meta.get('start', 0.0) or 0.0)), 2)
    end = round(max([float(meta.get('end', start) or start)] + [s['end'] for s in cleaned]), 2) if cleaned else round(max(start, float(meta.get('end', start) or start)), 2)
    speaker_ids, speaker_names = expected_speaker_meta(kind)
    raw_segment_count = meta.get('raw_segment_count')
    if not isinstance(raw_segment_count, int):
        raw_segment_count = len(cleaned)
    notes = meta.get('notes') if isinstance(meta.get('notes'), str) else ''
    if note_suffix not in notes:
        notes = (notes + ('; ' if notes else '') + note_suffix).strip()

    return {
        'meta': {
            'source_file': source_file,
            'index': infer_index(path, meta),
            'kind': kind,
            'persona': infer_persona(path, kind, meta),
            'title': infer_title(path, meta),
            'start': start,
            'end': end,
            'start_ts': ts(start),
            'end_ts': ts(end),
            'raw_segment_count': int(raw_segment_count),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentence_count': len(cleaned),
            'notes': notes,
        },
        'sentences': cleaned,
    }


def parse_raw_txt(path: Path) -> list[dict[str, Any]]:
    out = []
    pat = re.compile(r'^\[(\d+)\]\s+(\d{2}:\d{2}:\d{2}\.\d{2})\s+-\s+(\d{2}:\d{2}:\d{2}\.\d{2})\s+(\S+)\s+\|\s*(.*)$')
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        _, s0, s1, speaker, text = m.groups()
        out.append({
            'start': round(parse_ts(s0), 2),
            'end': round(parse_ts(s1), 2),
            'speaker': speaker,
            'text': text,
        })
    return out


def find_raw_section(path: Path) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]] | None]:
    stem = path.stem
    candidates = [
        path.parent / '_raw_sections_corrected' / f'{stem}.json',
        path.parent / '_raw_sections_corrected' / f'{stem}.txt',
        path.parent / '_raw_sections' / f'{stem}.json',
        path.parent / '_raw_sections' / f'{stem}.txt',
    ]
    for cand in candidates:
        if not cand.exists():
            continue
        if cand.suffix == '.json':
            try:
                obj = json.loads(cand.read_text(encoding='utf-8'))
            except Exception:
                continue
            meta = obj.get('meta', {}) if isinstance(obj, dict) else {}
            raw = obj.get('raw_segments', []) if isinstance(obj, dict) else []
            if isinstance(meta, dict) and isinstance(raw, list):
                return 'json', meta, [x for x in raw if isinstance(x, dict)]
        else:
            raw = parse_raw_txt(cand)
            if raw:
                return 'txt', None, raw
    return '', None, None


def host_labels_from_hostonly_raw(dir_path: Path) -> set[str]:
    totals: dict[str, float] = {}
    raw_dirs = [dir_path / '_raw_sections_corrected', dir_path / '_raw_sections']
    for raw_dir in raw_dirs:
        if not raw_dir.exists():
            continue
        for cand in raw_dir.iterdir():
            if cand.suffix not in {'.json', '.txt'}:
                continue
            kind = infer_kind(Path(cand.name))
            if kind == 'call':
                continue
            if cand.suffix == '.json':
                try:
                    obj = json.loads(cand.read_text(encoding='utf-8'))
                    raw = obj.get('raw_segments', [])
                except Exception:
                    continue
            else:
                raw = parse_raw_txt(cand)
            for seg in raw:
                if not isinstance(seg, dict):
                    continue
                text = '' if seg.get('text') is None else str(seg.get('text'))
                if not text.strip():
                    continue
                spk = str(seg.get('speaker', ''))
                dur = max(0.0, float(seg.get('end', 0.0) or 0.0) - float(seg.get('start', 0.0) or 0.0))
                totals[spk] = totals.get(spk, 0.0) + max(dur, len(text) / 10)
    if not totals:
        return set()
    maxv = max(totals.values())
    return {k for k, v in totals.items() if v >= maxv * 0.15}


def source_json_for_dir(dir_path: Path) -> Path | None:
    name = dir_path.name.removesuffix('_processed')
    p = dir_path.parent / f'{name}.json'
    return p if p.exists() else None


def host_labels_from_source_overlap(dir_path: Path, source_json: Path) -> set[str]:
    try:
        source = json.loads(source_json.read_text(encoding='utf-8'))
    except Exception:
        return set()
    segments = [s for s in source.get('segments', []) if isinstance(s, dict)]
    if not segments:
        return set()
    votes: dict[str, dict[str, float]] = {}
    for f in dir_path.glob('*.json'):
        try:
            obj = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(obj, dict) or 'meta' not in obj or 'sentences' not in obj:
            continue
        for sent in obj.get('sentences', []):
            if not isinstance(sent, dict):
                continue
            sid = str(sent.get('speaker_id', ''))
            if sid not in {'host', 'guest'}:
                continue
            s0 = float(sent.get('start', 0.0) or 0.0)
            s1 = float(sent.get('end', s0) or s0)
            for seg in segments:
                mid = (float(seg.get('start', 0.0) or 0.0) + float(seg.get('end', 0.0) or 0.0)) / 2
                if s0 - 0.05 <= mid <= s1 + 0.05:
                    spk = str(seg.get('speaker', ''))
                    text = '' if seg.get('text') is None else str(seg.get('text'))
                    w = max(1.0, len(text) / 6)
                    votes.setdefault(spk, {'host': 0.0, 'guest': 0.0})[sid] += w
    labels = {spk for spk, vv in votes.items() if vv['host'] > vv['guest']}
    return labels


def merge_segments(raw_segments: list[dict[str, Any]], kind: str, host_labels: set[str]) -> list[dict[str, Any]]:
    sents = []
    for seg in raw_segments:
        text = '' if seg.get('text') is None else str(seg.get('text'))
        if not text.strip():
            continue
        start = round(max(0.0, float(seg.get('start', 0.0) or 0.0)), 2)
        end = round(max(start, float(seg.get('end', start) or start)), 2)
        raw_spk = str(seg.get('speaker', ''))
        if kind == 'call':
            sid = 'host' if raw_spk in host_labels else 'guest'
        else:
            sid = 'host'
        sents.append({'speaker_id': sid, 'speaker_name': HOST_NAME if sid == 'host' else GUEST_NAME, 'start': start, 'end': end, 'text': text.strip()})
    sents.sort(key=lambda x: (x['start'], x['end'], x['speaker_id']))
    merged = []
    for s in sents:
        if merged and merged[-1]['speaker_id'] == s['speaker_id'] and s['start'] - merged[-1]['end'] <= 0.6:
            merged[-1]['end'] = max(merged[-1]['end'], s['end'])
            merged[-1]['text'] = (merged[-1]['text'] + s['text']).strip()
        else:
            merged.append(dict(s))
    return merged


def rebuild_from_raw(path: Path) -> dict[str, Any] | None:
    source_kind, raw_meta, raw_segments = find_raw_section(path)
    if not raw_segments:
        return None
    kind = infer_kind(path, raw_meta or {})
    dir_path = path.parent
    host_labels = host_labels_from_hostonly_raw(dir_path)
    source_json = source_json_for_dir(dir_path)
    if not host_labels and source_json is not None:
        host_labels = host_labels_from_source_overlap(dir_path, source_json)
    if not host_labels and kind == 'call':
        first = next((str(x.get('speaker', '')) for x in raw_segments if str(x.get('text', '')).strip()), '')
        if first:
            host_labels = {first}
    sentences = merge_segments(raw_segments, kind, host_labels)
    if not sentences:
        return None
    start = round(min(s['start'] for s in sentences), 2)
    end = round(max(s['end'] for s in sentences), 2)
    speaker_ids, speaker_names = expected_speaker_meta(kind)
    meta = raw_meta or {}
    notes = meta.get('notes') if isinstance(meta.get('notes'), str) else ''
    suffix = f'qc_rebuild_v1: rebuilt from sibling raw sections ({source_kind}); text preserved from raw segments.'
    if suffix not in notes:
        notes = (notes + ('; ' if notes else '') + suffix).strip()
    source_file = normalize_source_file(meta, (source_json.name if source_json else path.parent.name.removesuffix('_processed') + '.json'))
    return {
        'meta': {
            'source_file': source_file,
            'index': infer_index(path, meta),
            'kind': kind,
            'persona': infer_persona(path, kind, meta),
            'title': infer_title(path, meta),
            'start': start,
            'end': end,
            'start_ts': ts(start),
            'end_ts': ts(end),
            'raw_segment_count': int(meta.get('raw_segment_count', len(raw_segments))) if isinstance(meta.get('raw_segment_count', len(raw_segments)), int) else len(raw_segments),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentence_count': len(sentences),
            'notes': notes,
        },
        'sentences': sentences,
    }


def rebuild_from_source(path: Path) -> dict[str, Any] | None:
    dir_path = path.parent
    source_json = source_json_for_dir(dir_path)
    if source_json is None:
        return None
    try:
        source = json.loads(source_json.read_text(encoding='utf-8'))
    except Exception:
        return None
    source_segments = [s for s in source.get('segments', []) if isinstance(s, dict)]
    if not source_segments:
        return None

    idx = infer_index(path)
    prev_end = None
    next_start = None
    for sib in sorted(dir_path.glob('*.json')):
        if sib == path:
            continue
        try:
            obj = json.loads(sib.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(obj, dict) or 'meta' not in obj:
            continue
        meta = obj['meta']
        if not isinstance(meta, dict):
            continue
        sib_idx = infer_index(sib, meta)
        st = meta.get('start')
        ed = meta.get('end')
        if not isinstance(st, (int, float)) or not isinstance(ed, (int, float)):
            continue
        if sib_idx < idx:
            prev_end = max(prev_end, float(ed)) if prev_end is not None else float(ed)
        elif sib_idx > idx:
            next_start = min(next_start, float(st)) if next_start is not None else float(st)
    all_starts = [float(s.get('start', 0.0) or 0.0) for s in source_segments]
    all_ends = [float(s.get('end', 0.0) or 0.0) for s in source_segments]
    start = prev_end if prev_end is not None else min(all_starts)
    end = next_start if next_start is not None else max(all_ends)
    if end <= start:
        return None

    kind = infer_kind(path)
    host_labels = host_labels_from_hostonly_raw(dir_path)
    if not host_labels:
        host_labels = host_labels_from_source_overlap(dir_path, source_json)
    picked = []
    for seg in source_segments:
        text = '' if seg.get('text') is None else str(seg.get('text'))
        if not text.strip():
            continue
        s0 = float(seg.get('start', 0.0) or 0.0)
        s1 = float(seg.get('end', s0) or s0)
        if s1 < start or s0 > end:
            continue
        picked.append({'start': s0, 'end': s1, 'speaker': str(seg.get('speaker', '')), 'text': text})
    if not picked:
        return None
    if not host_labels and kind == 'call':
        first = next((str(x.get('speaker', '')) for x in picked if str(x.get('text', '')).strip()), '')
        if first:
            host_labels = {first}
    sentences = merge_segments(picked, kind, host_labels)
    if not sentences:
        return None
    start = round(min(s['start'] for s in sentences), 2)
    end = round(max(s['end'] for s in sentences), 2)
    speaker_ids, speaker_names = expected_speaker_meta(kind)
    return {
        'meta': {
            'source_file': source_json.name,
            'index': idx,
            'kind': kind,
            'persona': infer_persona(path, kind),
            'title': infer_title(path),
            'start': start,
            'end': end,
            'start_ts': ts(start),
            'end_ts': ts(end),
            'raw_segment_count': len(picked),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentence_count': len(sentences),
            'notes': 'qc_rebuild_v1: rebuilt from source transcript using neighboring section boundaries; text preserved from source segments.',
        },
        'sentences': sentences,
    }


def move_artifact_dirs() -> list[str]:
    moved = []
    for p in YEAR_ROOT.iterdir():
        if not p.is_dir():
            continue
        if not any(tok in p.name for tok in ARTIFACT_PATTERNS):
            continue
        dst = backup_dir_move(p)
        if dst.exists():
            continue
        shutil.move(str(p), str(dst))
        moved.append(str(p.relative_to(TRANSCRIPTS_ROOT)))
    return moved


def main() -> None:
    moved_dirs = move_artifact_dirs()
    changed = []
    failed = []
    note_suffix = 'qc_safe_fix_v1: normalized 2023 formal schema fields, removed empty sentences, and aligned section boundaries.'

    for rec in load_records():
        if rec.get('qc_status') not in {'warn', 'fail'}:
            continue
        rel = rec['path']
        if any(tok in rel for tok in ARTIFACT_PATTERNS):
            continue
        path = TRANSCRIPTS_ROOT / rel
        if not path.exists():
            continue
        issues = {i.get('code') for i in rec.get('issues', [])}
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            obj = None

        new_obj = None
        repair_kind = None
        if obj is None:
            new_obj = rebuild_from_raw(path) or rebuild_from_source(path)
            repair_kind = 'rebuild' if new_obj is not None else None
        else:
            large_count_mismatch = False
            for i in rec.get('issues', []):
                if i.get('code') == 'sentence_count_mismatch':
                    m = re.search(r'meta\.sentence_count=(\d+) but len\(sentences\)=(\d+)', i.get('message', ''))
                    if m and abs(int(m.group(1)) - int(m.group(2))) > 3:
                        large_count_mismatch = True
            if large_count_mismatch:
                new_obj = rebuild_from_raw(path) or normalize_loaded_obj(path, obj, note_suffix)
                repair_kind = 'rebuild_or_normalize'
            elif issues & {'sentence_count_mismatch', 'sentence_outside_section', 'schema_validation_error', 'empty_sentence_text'}:
                new_obj = normalize_loaded_obj(path, obj, note_suffix)
                repair_kind = 'normalize'

        if new_obj is None:
            failed.append({'path': rel, 'reason': 'unable_to_repair'})
            continue
        backup(path)
        path.write_text(json.dumps(new_obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append({'path': rel, 'repair': repair_kind, 'issue_codes': sorted(issues)})

    out = ROOT / 'data/04_check_v1/2023_fix_safe_report.json'
    out.write_text(json.dumps({'moved_dirs': moved_dirs, 'changed_count': len(changed), 'failed_count': len(failed), 'changed': changed, 'failed': failed}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'moved_dirs': len(moved_dirs), 'changed_count': len(changed), 'failed_count': len(failed)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
