#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2022_warn_gt3s_20260325'


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


def load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def save(path: str, obj: dict[str, Any]) -> None:
    p = ROOT / path
    backup(p)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sort_sentences(obj: dict[str, Any]) -> None:
    obj['sentences'].sort(key=lambda x: (float(x['start']), float(x['end']), x.get('speaker_id', '')))


def refresh_meta(obj: dict[str, Any]) -> None:
    sents = obj['sentences']
    obj['meta']['sentence_count'] = len(sents)
    if sents:
        obj['meta']['start'] = round(float(min(float(s['start']) for s in sents)), 2)
        obj['meta']['end'] = round(float(max(float(s['end']) for s in sents)), 2)
        obj['meta']['start_ts'] = ts(obj['meta']['start'])
        obj['meta']['end_ts'] = ts(obj['meta']['end'])


def append_note(obj: dict[str, Any], note: str) -> None:
    old = obj['meta'].get('notes') if isinstance(obj['meta'].get('notes'), str) else ''
    if note not in old:
        obj['meta']['notes'] = (old + ('; ' if old else '') + note).strip()


def main() -> None:
    changed = []

    # 1) 54/06: section boundary cut too late; recut comment start to first kept sentence.
    p54_06 = 'data/03_transcripts/曲曲2022/54 - 曲曲大女人 2022年12月20日 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡 #曲曲_processed/06_旧爱回头女_评论.json'
    obj = load(p54_06)
    sort_sentences(obj)
    refresh_meta(obj)
    append_note(obj, 'qc_warn_fix_v2: recut comment boundary to actual first sentence; no text changed.')
    save(p54_06, obj)
    changed.append(p54_06)

    # 2) 34/03: trailing sentence belongs to following comment; remove duplicated overlap from call.
    p34_03 = 'data/03_transcripts/曲曲2022/34 - 曲曲大女人 2022年11月05日 高清分案例版  #曲曲麦肯锡 #曲曲麦肯锡2022_processed/03_33岁海外女生无身份求方向_连麦.json'
    obj = load(p34_03)
    obj['sentences'] = [s for s in obj['sentences'] if not (abs(float(s['start']) - 3467.70) < 0.02 and abs(float(s['end']) - 3471.03) < 0.02)]
    sort_sentences(obj)
    refresh_meta(obj)
    append_note(obj, 'qc_warn_fix_v2: removed trailing overlap sentence that belongs to following comment section.')
    save(p34_03, obj)
    changed.append(p34_03)

    # 3) 51/18 + 19: host greeting lines belong to next call, move from comment to next call.
    p51_18 = 'data/03_transcripts/曲曲2022/51 - 曲曲大女人 2022年12月13日 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺_processed/18_金贵学员推进关系女_评论.json'
    p51_19 = 'data/03_transcripts/曲曲2022/51 - 曲曲大女人 2022年12月13日 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺_processed/19_29岁离异复盘女_连麦.json'
    c18 = load(p51_18)
    c19 = load(p51_19)
    moved_18 = [s for s in c18['sentences'] if float(s['start']) >= 10103.38]
    c18['sentences'] = [s for s in c18['sentences'] if float(s['start']) < 10103.38]
    c19['sentences'] = moved_18 + c19['sentences']
    sort_sentences(c18)
    sort_sentences(c19)
    refresh_meta(c18)
    refresh_meta(c19)
    append_note(c18, 'qc_warn_fix_v2: moved next-call greeting lines out of comment section.')
    append_note(c19, 'qc_warn_fix_v2: prepended host greeting lines moved from previous comment section.')
    save(p51_18, c18)
    save(p51_19, c19)
    changed.extend([p51_18, p51_19])

    # 4) 51/22: keep only the true comment close; later host lines belong to next call / audio check.
    p51_22 = 'data/03_transcripts/曲曲2022/51 - 曲曲大女人 2022年12月13日 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺_processed/22_一线人脉变现女_评论.json'
    obj = load(p51_22)
    obj['sentences'] = [s for s in obj['sentences'] if float(s['start']) <= 12457.89]
    sort_sentences(obj)
    refresh_meta(obj)
    append_note(obj, 'qc_warn_fix_v2: removed next-call audio-check lines from comment section; kept true comment close only.')
    save(p51_22, obj)
    changed.append(p51_22)

    report = {
        'changed_count': len(changed),
        'changed_files': changed,
    }
    out = ROOT / 'data/04_check_v1/2022_warn_gt3s_fix_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
