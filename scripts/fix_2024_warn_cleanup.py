#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
RECORDS = ROOT / 'data/04_check_v1/2024_records.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2024_warn_cleanup_20260325'


def ts(seconds: float) -> str:
    total = round(max(0.0, float(seconds)), 2)
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


def normalize_formal_file(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8'))
    meta = obj['meta']
    sentences = obj['sentences']

    cleaned = []
    removed_empty = 0
    for s in sentences:
        text = '' if s.get('text') is None else str(s.get('text'))
        if not text.strip():
            removed_empty += 1
            continue
        item = {
            'speaker_id': s.get('speaker_id'),
            'speaker_name': s.get('speaker_name'),
            'start': float(s.get('start', 0.0)),
            'end': float(s.get('end', 0.0)),
            'text': text,
        }
        if item['end'] < item['start']:
            item['end'] = item['start']
        cleaned.append(item)

    cleaned.sort(key=lambda x: (x['start'], x['end'], str(x['speaker_id'])))

    old_start = float(meta.get('start', 0.0) or 0.0)
    old_end = float(meta.get('end', old_start) or old_start)

    if cleaned:
        new_start = max(0.0, min(x['start'] for x in cleaned))
        new_end = max(new_start, max(x['end'] for x in cleaned))
    else:
        new_start = max(0.0, old_start)
        new_end = max(new_start, old_end)

    meta['start'] = round(new_start, 2)
    meta['end'] = round(new_end, 2)
    meta['start_ts'] = ts(meta['start'])
    meta['end_ts'] = ts(meta['end'])
    meta['sentence_count'] = len(cleaned)

    note = meta.get('notes') if isinstance(meta.get('notes'), str) else ''
    suffix = 'qc_warn_cleanup_v1: removed empty sentences and aligned section boundary to remaining sentences.'
    if suffix not in note:
        meta['notes'] = (note + ('; ' if note else '') + suffix).strip()

    obj['meta'] = meta
    obj['sentences'] = cleaned
    return {
        'obj': obj,
        'removed_empty': removed_empty,
        'old_start': old_start,
        'old_end': old_end,
        'new_start': new_start,
        'new_end': new_end,
        'new_sentence_count': len(cleaned),
    }


def main() -> None:
    changed = []
    total_removed_empty = 0
    for line in RECORDS.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('qc_status') != 'warn':
            continue
        rel = rec['path']
        path = TRANSCRIPTS_ROOT / rel
        backup(path)
        res = normalize_formal_file(path)
        path.write_text(json.dumps(res['obj'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        total_removed_empty += res['removed_empty']
        changed.append({
            'path': rel,
            'removed_empty': res['removed_empty'],
            'old_start': res['old_start'],
            'old_end': res['old_end'],
            'new_start': res['new_start'],
            'new_end': res['new_end'],
            'new_sentence_count': res['new_sentence_count'],
        })

    out = ROOT / 'data/04_check_v1/2024_warn_cleanup_report.json'
    out.write_text(json.dumps({
        'changed_count': len(changed),
        'total_removed_empty': total_removed_empty,
        'changed': changed,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'changed_count': len(changed),
        'total_removed_empty': total_removed_empty,
        'report': str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
