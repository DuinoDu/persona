#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
RECORDS = ROOT / 'data/04_check_v1/2025_records.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2025_warn_lt3_20260325'
THRESHOLD = 3.0


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


def max_gap_from_issues(issues: list[dict]) -> float:
    max_gap = 0.0
    for issue in issues:
        if issue.get('code') != 'sentence_outside_section':
            continue
        m = re.search(r'sentence \[([0-9.]+), ([0-9.]+)\] outside section \[([0-9.]+), ([0-9.]+)\]', issue.get('message',''))
        if not m:
            continue
        s0, s1, a0, a1 = map(float, m.groups())
        gap = max(max(0.0, a0 - s0), max(0.0, s1 - a1))
        max_gap = max(max_gap, gap)
    return max_gap


def main() -> None:
    changed = []
    skipped = []
    for line in RECORDS.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get('qc_status') != 'warn':
            continue
        issues = rec.get('issues', [])
        has_empty = any(i.get('code') == 'empty_sentence_text' for i in issues)
        max_gap = max_gap_from_issues(issues)
        if max_gap >= THRESHOLD and not has_empty:
            skipped.append({'path': rec['path'], 'reason': 'has_ge_3s_gap', 'max_gap': round(max_gap, 2)})
            continue
        if max_gap >= THRESHOLD and has_empty:
            skipped.append({'path': rec['path'], 'reason': 'has_ge_3s_gap_even_with_empty', 'max_gap': round(max_gap, 2)})
            continue
        rel = rec['path']
        path = TRANSCRIPTS_ROOT / rel
        obj = json.loads(path.read_text(encoding='utf-8'))
        sents = obj.get('sentences', [])
        backup(path)
        cleaned = []
        removed_empty = 0
        for s in sents:
            text = '' if s.get('text') is None else str(s.get('text'))
            if not text.strip():
                removed_empty += 1
                continue
            start = round(max(0.0, float(s.get('start', 0.0))), 2)
            end = round(max(start, float(s.get('end', start))), 2)
            s['start'] = start
            s['end'] = end
            s['text'] = text
            cleaned.append(s)
        cleaned.sort(key=lambda x: (float(x['start']), float(x['end']), str(x.get('speaker_id',''))))
        obj['sentences'] = cleaned
        obj['meta']['sentence_count'] = len(cleaned)
        if cleaned:
            new_start = round(min(float(s['start']) for s in cleaned), 2)
            new_end = round(max(float(s['end']) for s in cleaned), 2)
            obj['meta']['start'] = new_start
            obj['meta']['end'] = new_end
            obj['meta']['start_ts'] = ts(new_start)
            obj['meta']['end_ts'] = ts(new_end)
        note = obj['meta'].get('notes') if isinstance(obj['meta'].get('notes'), str) else ''
        suffix = 'qc_warn_fix_v1: removed empty sentences and aligned section boundary for <3s overlaps.'
        if suffix not in note:
            obj['meta']['notes'] = (note + ('; ' if note else '') + suffix).strip()
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed.append({'path': rel, 'removed_empty': removed_empty, 'max_gap': round(max_gap, 2)})
    out = ROOT / 'data/04_check_v1/2025_warn_lt3_fix_report.json'
    out.write_text(json.dumps({'changed_count': len(changed), 'skipped_count': len(skipped), 'changed': changed, 'skipped': skipped}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'changed_count': len(changed), 'skipped_count': len(skipped)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
