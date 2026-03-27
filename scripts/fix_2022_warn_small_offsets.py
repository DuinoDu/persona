#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
YEAR_ROOT = ROOT / 'data/03_transcripts/曲曲2022'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2022_warn_20260325'
THRESHOLD = 1.0  # strictly < 1.0 sec


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

    records_path = ROOT / 'data/04_check_v1/2022_records.jsonl'
    for line in records_path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('qc_status') != 'warn':
            continue
        rel = rec['path']
        path = ROOT / 'data/03_transcripts' / rel
        obj = json.loads(path.read_text(encoding='utf-8'))
        meta = obj['meta']
        sentences = obj['sentences']
        if not sentences:
            skipped.append({'path': rel, 'reason': 'empty_sentences'})
            continue

        cur_start = float(meta['start'])
        cur_end = float(meta['end'])
        min_start = min(float(s['start']) for s in sentences)
        max_end = max(float(s['end']) for s in sentences)
        start_gap = cur_start - min_start if min_start < cur_start else 0.0
        end_gap = max_end - cur_end if max_end > cur_end else 0.0

        new_start = cur_start
        new_end = cur_end
        changed_sides = []

        if 0 < start_gap < THRESHOLD:
            new_start = min_start
            changed_sides.append({'side': 'start', 'old': cur_start, 'new': new_start, 'gap': start_gap})
        if 0 < end_gap < THRESHOLD:
            new_end = max_end
            changed_sides.append({'side': 'end', 'old': cur_end, 'new': new_end, 'gap': end_gap})

        if not changed_sides:
            skipped.append({'path': rel, 'reason': 'no_gap_lt_1s', 'start_gap': start_gap, 'end_gap': end_gap})
            continue

        backup(path)
        meta['start'] = round(new_start, 2)
        meta['end'] = round(new_end, 2)
        meta['start_ts'] = ts(meta['start'])
        meta['end_ts'] = ts(meta['end'])
        note = meta.get('notes') if isinstance(meta.get('notes'), str) else ''
        suffix = 'qc_warn_fix_v1: expand meta boundary for <1s sentence_outside_section.'
        if suffix not in note:
            meta['notes'] = (note + ('; ' if note else '') + suffix).strip()
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append({'path': rel, 'changes': changed_sides})

    report = {
        'threshold_seconds': THRESHOLD,
        'changed_count': len(changed),
        'skipped_count': len(skipped),
        'changed': changed,
        'skipped': skipped,
    }
    out = ROOT / 'data/04_check_v1/2022_warn_fix_lt1s_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'changed_count': len(changed),
        'skipped_count': len(skipped),
        'report': out.as_posix(),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
