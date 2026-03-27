#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
RECORDS = ROOT / 'data/04_check_v1/2026_records.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2026_warn_20260325'


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


def main() -> None:
    changed = []
    for line in RECORDS.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('qc_status') != 'warn':
            continue
        rel = rec['path']
        path = TRANSCRIPTS_ROOT / rel
        obj = json.loads(path.read_text(encoding='utf-8'))
        sents = obj.get('sentences', [])
        if not sents:
            continue
        backup(path)
        for s in sents:
            s['start'] = round(max(0.0, float(s.get('start', 0.0))), 2)
            s['end'] = round(max(float(s['start']), float(s.get('end', s['start']))), 2)
        new_start = round(min(float(s['start']) for s in sents), 2)
        new_end = round(max(float(s['end']) for s in sents), 2)
        obj['meta']['start'] = new_start
        obj['meta']['end'] = new_end
        obj['meta']['start_ts'] = ts(new_start)
        obj['meta']['end_ts'] = ts(new_end)
        obj['meta']['sentence_count'] = len(sents)
        note = obj['meta'].get('notes') if isinstance(obj['meta'].get('notes'), str) else ''
        suffix = 'qc_warn_fix_v1: expanded section boundary to cover sentence spans.'
        if suffix not in note:
            obj['meta']['notes'] = (note + ('; ' if note else '') + suffix).strip()
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append(rel)
    out = ROOT / 'data/04_check_v1/2026_warn_fix_report.json'
    out.write_text(json.dumps({'changed_count': len(changed), 'changed': changed}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'changed_count': len(changed)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
