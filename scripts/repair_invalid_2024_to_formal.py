#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_ROOT = ROOT / 'data/03_transcripts'
INPUT_LIST = ROOT / 'invalid-2024.txt'
BACKUP_ROOT = ROOT / 'data/03_transcripts/_qc_fix_backups/曲曲2024_invalid2024_20260325'
HOST_NAME = '曲曲'
GUEST_NAME = '嘉宾'


def ts(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total = round(seconds, 2)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total - hours * 3600 - minutes * 60
    return f'{hours:02d}:{minutes:02d}:{secs:05.2f}'


def parse_time(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    # HH:MM:SS(.sss)
    m = re.match(r'^(\d+):(\d{2}):(\d{2})(?:\.(\d+))?$', s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        sec = int(m.group(3))
        frac = float('0.' + (m.group(4) or '0'))
        return h * 3600 + mi * 60 + sec + frac
    # MM:SS(.sss)
    m = re.match(r'^(\d+):(\d{2})(?:\.(\d+))?$', s)
    if m:
        mi = int(m.group(1))
        sec = int(m.group(2))
        frac = float('0.' + (m.group(3) or '0'))
        return mi * 60 + sec + frac
    try:
        return float(s)
    except Exception:
        return 0.0


def backup(path: Path) -> None:
    dst = BACKUP_ROOT / path.relative_to(ROOT)
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def get_year_source_basename(path: Path) -> str:
    for parent in [path.parent, *path.parents]:
        if parent == TRANSCRIPTS_ROOT:
            break
        candidate = parent.parent / f'{parent.name}.json'
        if candidate.exists():
            return candidate.name
    # fallback: remove _processed-like suffixes
    name = path.parent.name
    for suf in ['_processed', '_final', '_processed_formal', '_raw_sections', 'final_output', 'formal']:
        name = name.replace(suf, '')
    return f'{name}.json'


def clean_persona(text: str) -> str:
    s = (text or '').strip()
    s = s.replace('_final', '').replace('_formal', '').replace('_processed', '')
    s = re.sub(r'^(\d+[_ -]*)', '', s)
    s = s.replace('opening_', '').replace('comment_', '').replace('call_', '')
    s = s.replace('开场白', '开场').replace('主播开场', '开场').replace('直播开场', '开场')
    s = re.sub(r'_(连麦|评论)$', '', s)
    s = re.sub(r'(_000\d+_\d+.*)$', '', s)
    s = s.strip('_- ')
    return s


def infer_kind(path: Path, obj: dict[str, Any]) -> str:
    candidates = []
    for key in ['kind', 'section_type', 'segment_type', 'type']:
        if key in obj:
            candidates.append(obj.get(key))
    if isinstance(obj.get('meta'), dict):
        for key in ['kind', 'section_type', 'segment_type', 'type']:
            if key in obj['meta']:
                candidates.append(obj['meta'].get(key))
    if isinstance(obj.get('metadata'), dict):
        for key in ['segment_type']:
            if key in obj['metadata']:
                candidates.append(obj['metadata'].get(key))
    if isinstance(obj.get('section_info'), dict):
        candidates.append(obj['section_info'].get('kind'))
    for key in ['section_name', 'segment_name', 'name', 'description']:
        if key in obj:
            candidates.append(obj.get(key))
    if isinstance(obj.get('meta'), dict):
        for key in ['title', 'persona']:
            if key in obj['meta']:
                candidates.append(obj['meta'].get(key))
    candidates.append(path.stem)
    text = ' | '.join(str(x) for x in candidates if x is not None).lower()
    if any(k in text for k in ['opening', '开场']):
        return 'opening'
    if any(k in text for k in ['连麦', 'call']):
        return 'call'
    return 'comment'


def infer_index(path: Path, obj: dict[str, Any]) -> int:
    for container in [obj, obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('section_info') if isinstance(obj.get('section_info'), dict) else {}]:
        for key in ['index', 'section_index', 'segment_index']:
            v = container.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
    m = re.match(r'^(\d+)', path.stem)
    return int(m.group(1)) if m else 0


def infer_title(path: Path, obj: dict[str, Any]) -> str:
    for container in [obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('section_info') if isinstance(obj.get('section_info'), dict) else {}, obj]:
        for key in ['title', 'section_name', 'segment_name', 'name']:
            v = container.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return path.stem


def infer_persona(path: Path, obj: dict[str, Any], kind: str) -> str:
    if kind == 'opening':
        return '开场'
    for container in [obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('section_info') if isinstance(obj.get('section_info'), dict) else {}, obj]:
        for key in ['persona', 'guest_persona', 'description', 'section_name', 'segment_name', 'name']:
            v = container.get(key)
            if isinstance(v, str) and v.strip():
                return clean_persona(v)
    return clean_persona(path.stem)


def get_section_times(path: Path, obj: dict[str, Any], sents: list[dict[str, Any]]) -> tuple[float, float]:
    start = None
    end = None
    containers = [obj, obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}, obj.get('section_info') if isinstance(obj.get('section_info'), dict) else {}]
    for c in containers:
        for k in ['start', 'start_time', 'original_start']:
            if k in c and start is None:
                start = parse_time(c.get(k))
        for k in ['end', 'end_time', 'original_end']:
            if k in c and end is None:
                end = parse_time(c.get(k))
    if isinstance(obj.get('time_range'), dict):
        start = parse_time(obj['time_range'].get('start')) if start is None else start
        end = parse_time(obj['time_range'].get('end')) if end is None else end
    if sents:
        if start is None:
            start = min(x['start'] for x in sents)
        if end is None:
            end = max(x['end'] for x in sents)
    if start is None:
        start = 0.0
    if end is None:
        end = start
    return float(start), float(end)


def get_sentence_source_list(obj: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    for key in ['sentences', 'raw_segments', 'segments', 'turns', 'utterances', 'raw_turns']:
        v = obj.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)], key
    if isinstance(obj.get('meta'), dict):
        for key in ['segments', 'raw_segments', 'turns']:
            v = obj['meta'].get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)], key
    return [], 'none'


def host_aliases(obj: dict[str, Any]) -> set[str]:
    vals = {HOST_NAME, '主播', 'HOST', 'host', 'main_speaker'}
    for c in [obj, obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}]:
        for key in ['main_speaker', 'host', 'host_speaker']:
            v = c.get(key)
            if isinstance(v, str) and v:
                vals.add(v)
    for key in ['hosts']:
        v = obj.get(key)
        if isinstance(v, list):
            vals.update(str(x) for x in v if x)
    if isinstance(obj.get('speakers'), dict):
        s = obj['speakers']
        if isinstance(s.get('host'), str):
            vals.add(s['host'])
    if isinstance(obj.get('speaker_mapping'), dict):
        for raw, mapped in obj['speaker_mapping'].items():
            txt = str(mapped)
            if any(k in txt.lower() for k in ['host', '主播']) or '曲曲' in txt:
                vals.add(str(raw))
    if isinstance(obj.get('speaker_roles'), dict):
        for raw, mapped in obj['speaker_roles'].items():
            txt = str(mapped)
            if any(k in txt.lower() for k in ['host', '主播']) or '曲曲' in txt:
                vals.add(str(raw))
    return vals


def guest_aliases(obj: dict[str, Any]) -> set[str]:
    vals = {GUEST_NAME, '嘉宾', 'guest', 'GUEST', '用户'}
    for c in [obj, obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}]:
        for key in ['guest', 'guest_speaker']:
            v = c.get(key)
            if isinstance(v, str) and v:
                vals.add(v)
    for key in ['guests']:
        v = obj.get(key)
        if isinstance(v, list):
            vals.update(str(x) for x in v if x)
    if isinstance(obj.get('speakers'), dict):
        s = obj['speakers']
        guests = s.get('guests')
        if isinstance(guests, list):
            vals.update(str(x) for x in guests if x)
    if isinstance(obj.get('speaker_mapping'), dict):
        for raw, mapped in obj['speaker_mapping'].items():
            txt = str(mapped)
            if any(k in txt.lower() for k in ['guest', '嘉宾', '用户']):
                vals.add(str(raw))
    if isinstance(obj.get('speaker_roles'), dict):
        for raw, mapped in obj['speaker_roles'].items():
            txt = str(mapped)
            if any(k in txt.lower() for k in ['guest', '嘉宾', '用户']):
                vals.add(str(raw))
    return vals


def normalize_sentence(item: dict[str, Any], kind: str, host_set: set[str], guest_set: set[str], offset: float) -> dict[str, Any]:
    raw_speaker = item.get('speaker_id', item.get('speaker', item.get('role', item.get('name', ''))))
    raw_name = item.get('speaker_name', item.get('name', ''))
    raw_role = item.get('speaker_role', item.get('role', ''))
    speaker_str = '' if raw_speaker is None else str(raw_speaker)
    name_str = '' if raw_name is None else str(raw_name)
    role_str = '' if raw_role is None else str(raw_role)

    start = parse_time(item.get('start', item.get('start_time', 0.0)))
    end = parse_time(item.get('end', item.get('end_time', start)))
    if offset and start < offset and end <= (end - start + offset + 5):
        start += offset
        end += offset
    elif offset and start < 5 and end < offset + 5 and 'original_start' in item:
        start += offset
        end += offset
    if end < start:
        end = start

    text = item.get('text', '')
    text = '' if text is None else str(text)

    if item.get('is_host') is True:
        sid = 'host'
    elif item.get('is_host') is False:
        sid = 'guest'
    elif speaker_str in host_set or name_str in host_set or role_str in host_set or '曲曲' in name_str or '主播' in role_str:
        sid = 'host'
    elif speaker_str in guest_set or name_str in guest_set or role_str in guest_set or '嘉宾' in name_str or '用户' in name_str:
        sid = 'guest'
    elif speaker_str.lower().startswith('guest') or speaker_str.lower().startswith('g'):
        sid = 'guest'
    elif speaker_str.lower().startswith('host') or speaker_str.lower().startswith('h'):
        sid = 'host'
    elif speaker_str.lower() in {'unknown', 'other', 'system'}:
        sid = 'guest' if kind == 'call' else 'host'
    elif re.match(r'^(speaker_|SPEAKER_)?\d+', speaker_str):
        sid = 'guest' if kind == 'call' else 'host'
    else:
        sid = 'guest' if kind == 'call' else 'host'

    return {
        'speaker_id': sid,
        'speaker_name': HOST_NAME if sid == 'host' else GUEST_NAME,
        'start': round(start, 2),
        'end': round(end, 2),
        'text': text,
    }


def build_formal(path: Path, obj: dict[str, Any]) -> dict[str, Any]:
    kind = infer_kind(path, obj)
    raw_items, source_key = get_sentence_source_list(obj)
    host_set = host_aliases(obj)
    guest_set = guest_aliases(obj)

    offset = 0.0
    if 'original_start' in obj:
        offset = parse_time(obj.get('original_start'))
    elif isinstance(obj.get('meta'), dict) and 'original_start' in obj['meta']:
        offset = parse_time(obj['meta'].get('original_start'))

    sentences = [normalize_sentence(x, kind, host_set, guest_set, offset) for x in raw_items]
    sentences.sort(key=lambda x: (x['start'], x['end'], x['speaker_id']))

    start, end = get_section_times(path, obj, sentences)
    if sentences:
        start = min(start, sentences[0]['start'])
        end = max(end, sentences[-1]['end'])

    raw_segment_count = None
    for c in [obj, obj.get('meta') if isinstance(obj.get('meta'), dict) else {}, obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}, obj.get('section_info') if isinstance(obj.get('section_info'), dict) else {}]:
        for key in ['raw_segment_count', 'segment_count', 'num_segments', 'total_segments', 'total_sentences', 'sentence_count']:
            v = c.get(key)
            if isinstance(v, int):
                raw_segment_count = v
                break
        if raw_segment_count is not None:
            break
    if raw_segment_count is None:
        raw_segment_count = len(raw_items)

    meta_speaker_ids = ['host', 'guest'] if kind == 'call' else ['host']
    meta_speaker_names = {'host': HOST_NAME, 'guest': GUEST_NAME} if kind == 'call' else {'host': HOST_NAME}

    notes = f'auto_repaired_from_{source_key}: normalized from legacy/skip structure into formal_output schema.'

    return {
        'meta': {
            'source_file': get_year_source_basename(path),
            'index': infer_index(path, obj),
            'kind': kind,
            'persona': infer_persona(path, obj, kind),
            'title': infer_title(path, obj),
            'start': round(max(0.0, start), 2),
            'end': round(max(max(0.0, start), end), 2),
            'start_ts': ts(max(0.0, start)),
            'end_ts': ts(max(max(0.0, start), end)),
            'raw_segment_count': int(raw_segment_count),
            'speaker_ids': meta_speaker_ids,
            'speaker_names': meta_speaker_names,
            'sentence_count': len(sentences),
            'notes': notes,
        },
        'sentences': sentences,
    }


def main() -> None:
    paths = [p for p in INPUT_LIST.read_text(encoding='utf-8').splitlines() if p.strip()]
    changed = []
    failed = []
    for rel in paths:
        path = TRANSCRIPTS_ROOT / rel
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(obj, dict):
                failed.append({'path': rel, 'reason': 'not_object'})
                continue
            formal = build_formal(path, obj)
            backup(path)
            path.write_text(json.dumps(formal, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            changed.append(rel)
        except Exception as e:
            failed.append({'path': rel, 'reason': str(e)})
    report = {
        'input_count': len(paths),
        'changed_count': len(changed),
        'failed_count': len(failed),
        'failed': failed[:200],
    }
    out = ROOT / 'data/04_check_v1/repair_invalid_2024_to_formal_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
