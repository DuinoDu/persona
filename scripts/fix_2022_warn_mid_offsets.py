#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / 'data/04_check_v1/2022_records.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2022_warn_mid_20260325'


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


def main() -> None:
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for line in RECORDS.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('qc_status') != 'warn':
            continue

        max_gap = 0.0
        for issue in rec.get('issues', []):
            m = re.search(r'sentence \[([0-9.]+), ([0-9.]+)\] outside section \[([0-9.]+), ([0-9.]+)\]', issue['message'])
            if not m:
                continue
            s0, s1, a0, a1 = map(float, m.groups())
            gap = max(max(0.0, a0 - s0), max(0.0, s1 - a1))
            max_gap = max(max_gap, gap)

        if not (0 < max_gap <= 3.0):
            skipped.append({'path': rec['path'], 'reason': 'max_gap_not_in_0_3', 'max_gap': round(max_gap, 2)})
            continue

        path = ROOT / 'data/03_transcripts' / rec['path']
        obj = json.loads(path.read_text(encoding='utf-8'))
        sentences = obj.get('sentences', [])
        if not sentences:
            skipped.append({'path': rec['path'], 'reason': 'no_sentences'})
            continue

        old_start = float(obj['meta']['start'])
        old_end = float(obj['meta']['end'])
        new_start = round(min(float(s['start']) for s in sentences), 2)
        new_end = round(max(float(s['end']) for s in sentences), 2)

        if new_start == old_start and new_end == old_end:
            skipped.append({'path': rec['path'], 'reason': 'already_covered'})
            continue

        backup(path)
        obj['meta']['start'] = new_start
        obj['meta']['end'] = new_end
        obj['meta']['start_ts'] = ts(new_start)
        obj['meta']['end_ts'] = ts(new_end)
        note = obj['meta'].get('notes') if isinstance(obj['meta'].get('notes'), str) else ''
        suffix = 'qc_warn_fix_v3: expanded meta boundary to cover existing 1~3s sentence overlap.'
        if suffix not in note:
            obj['meta']['notes'] = (note + ('; ' if note else '') + suffix).strip()
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append({
            'path': rec['path'],
            'old_start': old_start,
            'old_end': old_end,
            'new_start': new_start,
            'new_end': new_end,
            'max_gap': round(max_gap, 2),
        })

    out = ROOT / 'data/04_check_v1/2022_warn_mid_fix_report.json'
    out.write_text(json.dumps({
        'changed_count': len(changed),
        'skipped_count': len(skipped),
        'changed': changed,
        'skipped': skipped,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'changed_count': len(changed), 'skipped_count': len(skipped)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
