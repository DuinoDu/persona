#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
YEAR = '曲曲2024（全）'
INVALID_PATH = ROOT / 'data/04_check_v1/2024_invalid.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2024_20260325_safe'
HOST_NAME = '曲曲'
GUEST_NAME = '嘉宾'


KIND_MAP = {
    'opening': 'opening',
    '开场': 'opening',
    'call': 'call',
    '连麦': 'call',
    'comment': 'comment',
    '评论': 'comment',
    'closing': 'comment',
    'commentary': 'comment',
    'ending': 'comment',
}


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f'{hours:02d}:{minutes:02d}:{secs:05.2f}'


def backup(path: Path) -> None:
    dst = BACKUP_ROOT / path.relative_to(ROOT)
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def load_invalid_paths() -> list[str]:
    out = []
    for line in INVALID_PATH.read_text(encoding='utf-8').splitlines():
        if line.strip():
            out.append(json.loads(line)['path'])
    return out


def infer_index(name: str, meta: dict[str, Any]) -> int:
    if isinstance(meta.get('index'), int):
        return meta['index']
    if isinstance(meta.get('section_index'), int):
        return meta['section_index']
    m = re.match(r'^(\d+)', name)
    if m:
        return int(m.group(1))
    return 0


def infer_kind(name: str, meta: dict[str, Any]) -> str:
    raw = meta.get('kind')
    if isinstance(raw, str) and raw in KIND_MAP:
        return KIND_MAP[raw]
    stem = name[:-5] if name.endswith('.json') else name
    low = stem.lower()
    if '开场' in stem or 'opening' in low or 'open' in low:
        return 'opening'
    if '连麦' in stem or 'call' in low:
        return 'call'
    if '评论' in stem or 'comment' in low or 'closing' in low or 'ending' in low:
        return 'comment'
    return 'comment'


def infer_persona(name: str, kind: str, meta: dict[str, Any]) -> str:
    persona = meta.get('persona')
    if isinstance(persona, str):
        return persona
    stem = name[:-5] if name.endswith('.json') else name
    stem = re.sub(r'_final$', '', stem)
    stem = re.sub(r'_formal$', '', stem)
    stem = re.sub(r'^(\d+_)?', '', stem)
    if kind == 'opening':
        return '开场'
    stem = stem.replace('opening_', '').replace('comment_', '').replace('call_', '')
    stem = stem.replace('开场_', '').replace('连麦_', '').replace('评论_', '')
    stem = re.sub(r'_(连麦|评论)$', '', stem)
    return stem or ''


def infer_title(path: Path, meta: dict[str, Any]) -> str:
    title = meta.get('title')
    if isinstance(title, str) and title.strip():
        return title.strip()
    return path.stem


def normalize_source_file(meta: dict[str, Any]) -> str:
    src = meta.get('source_file')
    if isinstance(src, str) and src.strip():
        return Path(src).name
    return ''


def expected_meta_speakers(kind: str) -> tuple[list[str], dict[str, str]]:
    if kind == 'call':
        return ['host', 'guest'], {'host': HOST_NAME, 'guest': GUEST_NAME}
    return ['host'], {'host': HOST_NAME}


def map_sentence_speaker(raw_id: Any, raw_name: Any, kind: str) -> str:
    sid = '' if raw_id is None else str(raw_id)
    sname = '' if raw_name is None else str(raw_name)
    sid_l = sid.lower()
    if sid in {'host', 'guest'}:
        return sid
    if '曲曲' in sname or sname == HOST_NAME:
        return 'host'
    if '系统' in sname or sid_l == 'system':
        return 'host'
    if '嘉宾' in sname or 'guest' in sid_l:
        return 'guest'
    if sname in {'未知', '其他', 'UNKNOWN'} or sid_l in {'unknown', 'other'}:
        return 'guest'
    if re.match(r'^(speaker_|SPEAKER_)\d+', sid) or re.match(r'^(speaker_|SPEAKER_)\d+', sname):
        return 'guest'
    if kind == 'call':
        return 'guest'
    return 'host'


def normalize_sentence(sentence: dict[str, Any], kind: str) -> dict[str, Any]:
    sid = map_sentence_speaker(sentence.get('speaker_id'), sentence.get('speaker_name'), kind)
    return {
        'speaker_id': sid,
        'speaker_name': HOST_NAME if sid == 'host' else GUEST_NAME,
        'start': float(sentence.get('start', 0.0) or 0.0),
        'end': float(sentence.get('end', 0.0) or 0.0),
        'text': '' if sentence.get('text') is None else str(sentence.get('text')),
    }


def normalize_file(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8'))
    meta = obj.get('meta', {}) if isinstance(obj, dict) else {}
    sentences = obj.get('sentences', []) if isinstance(obj, dict) else []
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(sentences, list):
        sentences = []

    kind = infer_kind(path.name, meta)
    speaker_ids, speaker_names = expected_meta_speakers(kind)
    normalized_sentences = [normalize_sentence(s, kind) for s in sentences if isinstance(s, dict)]
    normalized_sentences.sort(key=lambda x: (x['start'], x['end'], x['speaker_id']))

    start = float(meta.get('start', normalized_sentences[0]['start'] if normalized_sentences else 0.0) or 0.0)
    end = float(meta.get('end', normalized_sentences[-1]['end'] if normalized_sentences else start) or start)
    if normalized_sentences:
        # keep stated boundaries if sane, otherwise expand to cover data
        start = min(start, normalized_sentences[0]['start'])
        end = max(end, normalized_sentences[-1]['end'])

    notes = meta.get('notes')
    if not isinstance(notes, str):
        notes = ''
    suffix = 'qc_safe_fix_v1: normalized 2024 formal schema fields and speaker ids without rewriting text.'
    if suffix not in notes:
        notes = (notes + ('; ' if notes else '') + suffix).strip()

    raw_segment_count = meta.get('raw_segment_count')
    if not isinstance(raw_segment_count, int):
        raw_segment_count = meta.get('segment_count')
    if not isinstance(raw_segment_count, int):
        raw_segment_count = len(normalized_sentences)

    normalized = {
        'meta': {
            'source_file': normalize_source_file(meta),
            'index': infer_index(path.name, meta),
            'kind': kind,
            'persona': infer_persona(path.name, kind, meta),
            'title': infer_title(path, meta),
            'start': round(start, 2),
            'end': round(end, 2),
            'start_ts': ts(start),
            'end_ts': ts(end),
            'raw_segment_count': int(raw_segment_count),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentence_count': len(normalized_sentences),
            'notes': notes,
        },
        'sentences': normalized_sentences,
    }
    return normalized


def main() -> None:
    changed = []
    for rel in load_invalid_paths():
        path = TRANSCRIPTS_ROOT / rel
        backup(path)
        normalized = normalize_file(path)
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append(rel)
    out = ROOT / 'data/04_check_v1/2024_fix_safe_report.json'
    out.write_text(json.dumps({'changed_count': len(changed), 'changed': changed}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'changed_count': len(changed)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
