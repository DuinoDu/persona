#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
YEAR_ROOT = ROOT / 'data/03_transcripts/曲曲2022'
QC_INVALID = ROOT / 'data/04_check_v1/2022_invalid.jsonl'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2022_20260325'
HOST_NAME = '曲曲'
GUEST_NAME = '嘉宾'


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f'{hours:02d}:{minutes:02d}:{secs:05.2f}'


def load_invalid_records() -> list[dict[str, Any]]:
    records = []
    for line in QC_INVALID.read_text(encoding='utf-8').splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def backup_file(path: Path) -> None:
    dest = BACKUP_ROOT / path.relative_to(ROOT)
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parse_first_json_object(text: str) -> tuple[Any, str] | tuple[None, str]:
    try:
        obj, idx = json.JSONDecoder().raw_decode(text)
        return obj, text[idx:]
    except Exception:
        return None, text


def normalize_formal_object(obj: dict[str, Any], note_suffix: str | None = None) -> dict[str, Any]:
    meta = dict(obj['meta'])
    sentences = list(obj['sentences'])
    meta['sentence_count'] = len(sentences)
    if 'start' in meta:
        meta['start'] = float(meta['start'])
        meta['start_ts'] = ts(meta['start'])
    if 'end' in meta:
        meta['end'] = float(meta['end'])
        meta['end_ts'] = ts(meta['end'])
    if note_suffix:
        notes = meta.get('notes') if isinstance(meta.get('notes'), str) else ''
        meta['notes'] = (notes + ('; ' if notes else '') + note_suffix).strip()
    return {'meta': meta, 'sentences': sentences}


def find_episode_root_and_source(processed_file: Path) -> tuple[Path | None, Path | None]:
    parent = processed_file.parent
    if not parent.name.endswith('_processed'):
        return None, None
    source_stem = parent.name.removesuffix('_processed')
    source_json = parent.parent / f'{source_stem}.json'
    return parent, source_json if source_json.exists() else None


def load_section_plan(processed_dir: Path) -> dict[str, Any] | None:
    plan_path = processed_dir / '_section_plan.json'
    if not plan_path.exists():
        return None
    text = plan_path.read_text(encoding='utf-8', errors='replace')
    try:
        return json.loads(text)
    except Exception:
        return None


def section_from_plan(plan: dict[str, Any], filename: str) -> dict[str, Any] | None:
    for sec in plan.get('sections', []):
        title = sec.get('title')
        if title and f"{title}.json" == filename:
            return sec
        fn = sec.get('filename')
        if fn == filename:
            return sec
    return None


def infer_kind_persona_from_filename(filename: str) -> tuple[int, str, str, str]:
    stem = filename[:-5] if filename.endswith('.json') else filename
    m = re.match(r'^(\d+)_(.+)$', stem)
    if not m:
        raise ValueError(f'cannot parse filename: {filename}')
    idx = int(m.group(1))
    rest = m.group(2)
    if stem == '00_开场' or rest == '开场':
        return idx, 'opening', '开场', stem
    if rest.endswith('_连麦'):
        return idx, 'call', rest[:-3], stem
    if rest.endswith('_评论'):
        return idx, 'comment', rest[:-3], stem
    return idx, 'comment', rest, stem


def build_section_spec_for_29(processed_dir: Path, filename: str, source_json: Path) -> dict[str, Any] | None:
    # Only used for the corrupted 29/_section_plan.json + empty 03_第二位听众_连麦.json
    if '2022年10月25日' not in processed_dir.name:
        return None
    if filename != '03_第二位听众_连麦.json':
        return None
    meta2 = json.loads((processed_dir / '02_第一位听众_评论.json').read_text(encoding='utf-8'))['meta']
    source = json.loads(source_json.read_text(encoding='utf-8'))
    source_end = max(float(seg['end']) for seg in source['segments'])
    idx, kind, persona, title = infer_kind_persona_from_filename(filename)
    return {
        'index': idx,
        'kind': kind,
        'persona': persona,
        'title': title,
        'start': float(meta2['end']),
        'end': float(source_end),
        'start_ts': ts(float(meta2['end'])),
        'end_ts': ts(float(source_end)),
    }


def rebuild_from_source(processed_file: Path) -> dict[str, Any] | None:
    processed_dir, source_json = find_episode_root_and_source(processed_file)
    if processed_dir is None or source_json is None:
        return None

    plan = load_section_plan(processed_dir)
    spec = section_from_plan(plan, processed_file.name) if plan else None
    if spec is None:
        spec = build_section_spec_for_29(processed_dir, processed_file.name, source_json)
    if spec is None:
        return None

    source = json.loads(source_json.read_text(encoding='utf-8'))
    segments = source.get('segments', [])
    start = float(spec['start'])
    end = float(spec['end'])
    kind = spec['kind']
    persona = spec['persona']
    title = spec.get('title') or processed_file.stem
    index = int(spec['index'])

    picked = []
    for seg in segments:
        s = float(seg.get('start', 0))
        e = float(seg.get('end', 0))
        txt = str(seg.get('text', ''))
        if not txt.strip():
            continue
        if e < start or s > end:
            continue
        raw_speaker = str(seg.get('speaker', ''))
        if kind == 'call':
            speaker_id = 'host' if raw_speaker == HOST_NAME else 'guest'
            speaker_name = HOST_NAME if speaker_id == 'host' else GUEST_NAME
        else:
            speaker_id = 'host'
            speaker_name = HOST_NAME
        picked.append({
            'speaker_id': speaker_id,
            'speaker_name': speaker_name,
            'start': s,
            'end': e,
            'text': txt.strip(),
        })

    meta = {
        'source_file': source_json.name,
        'index': index,
        'kind': kind,
        'persona': persona,
        'title': title,
        'start': start,
        'end': end,
        'start_ts': ts(start),
        'end_ts': ts(end),
        'raw_segment_count': len(picked),
        'speaker_ids': ['host', 'guest'] if kind == 'call' else ['host'],
        'speaker_names': {'host': HOST_NAME, 'guest': GUEST_NAME} if kind == 'call' else {'host': HOST_NAME},
        'sentence_count': len(picked),
        'notes': 'qc_fix_v1: rebuilt from source transcript + section plan; text preserved from source segments.',
    }
    return {'meta': meta, 'sentences': picked}


def fix_corrupted_plan_29(processed_dir: Path) -> bool:
    plan_path = processed_dir / '_section_plan.json'
    if not plan_path.exists():
        return False
    text = plan_path.read_text(encoding='utf-8', errors='replace')
    try:
        json.loads(text)
        return False
    except Exception:
        pass
    if '2022年10月25日' not in processed_dir.name:
        return False
    source_json = processed_dir.parent / f"{processed_dir.name.removesuffix('_processed')}.json"
    if not source_json.exists():
        return False
    source = json.loads(source_json.read_text(encoding='utf-8'))
    source_end = max(float(seg['end']) for seg in source['segments'])
    meta0 = json.loads((processed_dir / '00_开场.json').read_text(encoding='utf-8'))['meta']
    meta1 = json.loads((processed_dir / '01_第一位听众_连麦.json').read_text(encoding='utf-8'))['meta']
    meta2 = json.loads((processed_dir / '02_第一位听众_评论.json').read_text(encoding='utf-8'))['meta']
    plan = {
        'source_file': source_json.name,
        'section_count': 4,
        'call_count': 2,
        'sections': [
            {
                'index': 0, 'kind': 'opening', 'persona': '开场', 'title': '00_开场',
                'start': meta0['start'], 'end': meta0['end'], 'start_ts': meta0['start_ts'], 'end_ts': meta0['end_ts'],
                'filename': '00_开场.json'
            },
            {
                'index': 1, 'kind': 'call', 'persona': '第一位听众', 'title': '01_第一位听众_连麦',
                'start': meta1['start'], 'end': meta1['end'], 'start_ts': meta1['start_ts'], 'end_ts': meta1['end_ts'],
                'filename': '01_第一位听众_连麦.json'
            },
            {
                'index': 2, 'kind': 'comment', 'persona': '第一位听众', 'title': '02_第一位听众_评论',
                'start': meta2['start'], 'end': meta2['end'], 'start_ts': meta2['start_ts'], 'end_ts': meta2['end_ts'],
                'filename': '02_第一位听众_评论.json'
            },
            {
                'index': 3, 'kind': 'call', 'persona': '第二位听众', 'title': '03_第二位听众_连麦',
                'start': meta2['end'], 'end': source_end, 'start_ts': ts(meta2['end']), 'end_ts': ts(source_end),
                'filename': '03_第二位听众_连麦.json'
            },
        ],
        'notes': 'qc_fix_v1: original _section_plan.json was a CLI log; rebuilt minimal valid plan from existing formal files + source end time.'
    }
    backup_file(plan_path)
    write_json(plan_path, plan)
    return True


def main() -> None:
    records = load_invalid_records()
    fixed = []
    unresolved = []

    # fix corrupted non-formal plan first
    p29 = YEAR_ROOT / '29 - 曲曲大女人 2022年10月25日 高清分章节版 #曲曲麦肯锡_processed'
    if fix_corrupted_plan_29(p29):
        fixed.append(str((p29 / '_section_plan.json').relative_to(ROOT)))

    for rec in records:
        rel = rec['path']
        path = ROOT / 'data/03_transcripts' / rel
        if not path.exists():
            unresolved.append((rel, 'missing_file'))
            continue

        if path.name == '_section_plan.json':
            # already handled above; make it non-failing JSON at least
            try:
                json.loads(path.read_text(encoding='utf-8'))
                continue
            except Exception:
                unresolved.append((rel, 'corrupted_plan_not_fixed'))
                continue

        # 1) empty file -> rebuild from source/plan
        if path.stat().st_size == 0:
            rebuilt = rebuild_from_source(path)
            if rebuilt is not None:
                backup_file(path)
                write_json(path, rebuilt)
                fixed.append(rel)
            else:
                unresolved.append((rel, 'empty_file_without_rebuild_spec'))
            continue

        text = path.read_text(encoding='utf-8', errors='replace')

        # 2) duplicated/garbled but first JSON object is formal
        obj, rest = parse_first_json_object(text)
        if isinstance(obj, dict) and 'meta' in obj and 'sentences' in obj:
            normalized = normalize_formal_object(
                obj,
                note_suffix='qc_fix_v1: normalized sentence_count and removed duplicated trailing JSON.' if rest.strip() else 'qc_fix_v1: normalized sentence_count.'
            )
            backup_file(path)
            write_json(path, normalized)
            fixed.append(rel)
            continue

        # 3) regular parseable JSON formal object
        try:
            obj2 = json.loads(text)
        except Exception:
            unresolved.append((rel, 'json_not_recoverable_by_first_object'))
            continue
        if isinstance(obj2, dict) and 'meta' in obj2 and 'sentences' in obj2:
            normalized = normalize_formal_object(obj2, note_suffix='qc_fix_v1: normalized sentence_count.')
            backup_file(path)
            write_json(path, normalized)
            fixed.append(rel)
        else:
            unresolved.append((rel, 'non_formal_json'))

    report = {
        'fixed_count': len(fixed),
        'unresolved_count': len(unresolved),
        'fixed': fixed,
        'unresolved': [{'path': p, 'reason': r} for p, r in unresolved],
    }
    report_path = ROOT / 'data/04_check_v1/2022_fix_report.json'
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
