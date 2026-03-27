#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / 'data/05_annotations'
DEFAULT_SCHEMA_DIR = ROOT / 'docs/annotation_v1/schemas'
DEFAULT_OUTPUT_DIR = ROOT / 'data/05_annotations/qc_v1'

SCHEMA_BY_RECORD_TYPE = {
    'conversation': 'conversation_record.schema.json',
    'turn_sft': 'turn_sft_record.schema.json',
    'style_label': 'style_label_record.schema.json',
    'preference_pair': 'preference_pair_record.schema.json',
    'benchmark_case': 'benchmark_record.schema.json',
}

ID_KEY_BY_RECORD_TYPE = {
    'conversation': 'conversation_id',
    'turn_sft': 'sample_id',
    'style_label': 'label_id',
    'preference_pair': 'pair_id',
    'benchmark_case': 'benchmark_id',
}


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            'severity': self.severity,
            'code': self.code,
            'path': self.path,
            'message': self.message,
        }


def normalize_path(path_items: Iterable[Any]) -> str:
    path_items = list(path_items)
    if not path_items:
        return '$'
    out = '$'
    for item in path_items:
        if isinstance(item, int):
            out += f'[{item}]'
        else:
            out += f'.{item}'
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='QC annotation JSON/JSONL records against schema + semantic rules.')
    p.add_argument('--input-dir', type=Path, default=DEFAULT_INPUT_DIR)
    p.add_argument('--schema-dir', type=Path, default=DEFAULT_SCHEMA_DIR)
    p.add_argument('--out-dir', type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument('--include-glob', default='*.jsonl', help='Glob under input-dir. Default: *.jsonl')
    p.add_argument('--exclude-glob', action='append', default=['qc_v1/*'], help='Exclude glob(s) relative to input-dir')
    return p.parse_args()


def load_validators(schema_dir: Path) -> dict[str, Draft202012Validator]:
    validators: dict[str, Draft202012Validator] = {}
    for record_type, schema_name in SCHEMA_BY_RECORD_TYPE.items():
        schema = json.loads((schema_dir / schema_name).read_text(encoding='utf-8'))
        validators[record_type] = Draft202012Validator(schema)
    return validators


def should_exclude(path: Path, input_dir: Path, exclude_globs: list[str]) -> bool:
    rel = path.relative_to(input_dir)
    return any(rel.match(g) for g in exclude_globs)


def iter_input_files(input_dir: Path, include_glob: str, exclude_globs: list[str]) -> list[Path]:
    files = []
    for p in sorted(input_dir.rglob(include_glob)):
        if p.is_file() and not should_exclude(p, input_dir, exclude_globs):
            files.append(p)
    return files


def iter_records_from_file(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if path.suffix == '.jsonl':
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            if not line.strip():
                continue
            yield lineno, json.loads(line)
        return

    obj = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(obj, list):
        for idx, item in enumerate(obj, start=1):
            yield idx, item
    elif isinstance(obj, dict):
        yield 1, obj
    else:
        raise ValueError(f'Unsupported top-level JSON type in {path}: {type(obj).__name__}')


def issue(severity: str, code: str, path: str, message: str) -> Issue:
    return Issue(severity=severity, code=code, path=path, message=message)


def validate_schema(record: dict[str, Any], validator: Draft202012Validator) -> list[Issue]:
    issues: list[Issue] = []
    errors = sorted(validator.iter_errors(record), key=lambda e: (list(e.path), e.message))
    for err in errors:
        issues.append(issue('error', 'schema_validation_error', normalize_path(err.path), err.message))
    return issues


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def check_turn_sequence(turns: list[dict[str, Any]], base_path: str) -> list[Issue]:
    issues: list[Issue] = []
    prev_role = None
    prev_end = None
    for idx, turn in enumerate(turns):
        t_index = turn.get('turn_index')
        if t_index != idx:
            issues.append(issue('error', 'turn_index_not_sequential', f'{base_path}[{idx}].turn_index', f'expected {idx}, got {t_index}'))
        role = turn.get('role')
        speaker_id = turn.get('speaker_id')
        if role == 'persona' and speaker_id != 'host':
            issues.append(issue('error', 'role_speaker_mismatch', f'{base_path}[{idx}]', 'persona turn must have speaker_id=host'))
        if role == 'user' and speaker_id != 'guest':
            issues.append(issue('error', 'role_speaker_mismatch', f'{base_path}[{idx}]', 'user turn must have speaker_id=guest'))
        start = turn.get('start')
        end = turn.get('end')
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and start > end:
            issues.append(issue('error', 'turn_time_reversed', f'{base_path}[{idx}]', f'turn start {start} > end {end}'))
        if prev_role is not None and role == prev_role:
            issues.append(issue('error', 'adjacent_same_role_turns', f'{base_path}[{idx}]', 'adjacent turns should already be merged by speaker'))
        if prev_end is not None and isinstance(start, (int, float)) and start < prev_end - 1e-6:
            issues.append(issue('warning', 'turn_time_overlap', f'{base_path}[{idx}]', f'turn start {start} overlaps previous end {prev_end}'))
        prev_role = role
        if isinstance(end, (int, float)):
            prev_end = end
    return issues


def validate_record_semantics(record: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    record_type = record.get('record_type')

    audit = record.get('audit')
    if isinstance(audit, dict):
        created = parse_dt(audit.get('created_at'))
        updated = parse_dt(audit.get('updated_at'))
        if created and updated and updated < created:
            issues.append(issue('error', 'audit_time_reversed', '$.audit', 'updated_at is earlier than created_at'))

    if record_type == 'conversation':
        turns = record.get('turns', [])
        issues.extend(check_turn_sequence(turns, '$.turns'))
        source = record.get('source', {})
        sec_start = source.get('start')
        sec_end = source.get('end')
        for idx, turn in enumerate(turns):
            start = turn.get('start')
            end = turn.get('end')
            if isinstance(sec_start, (int, float)) and isinstance(start, (int, float)) and start < sec_start - 1e-6:
                issues.append(issue('warning', 'turn_outside_section', f'$.turns[{idx}]', f'turn start {start} < source.start {sec_start}'))
            if isinstance(sec_end, (int, float)) and isinstance(end, (int, float)) and end > sec_end + 1e-6:
                issues.append(issue('warning', 'turn_outside_section', f'$.turns[{idx}]', f'turn end {end} > source.end {sec_end}'))

    elif record_type == 'turn_sft':
        history = record.get('history', [])
        issues.extend(check_turn_sequence(history, '$.history'))
        if history and history[-1].get('role') != 'user':
            issues.append(issue('error', 'history_must_end_with_user', '$.history', 'history should end with a user turn'))
        target = record.get('target_reply', {})
        source = record.get('source', {})
        start = target.get('start')
        end = target.get('end')
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and start > end:
            issues.append(issue('error', 'target_time_reversed', '$.target_reply', f'target start {start} > end {end}'))
        if target.get('turn_index') != source.get('turn_index'):
            issues.append(issue('error', 'target_turn_index_mismatch', '$.target_reply.turn_index', 'target_reply.turn_index must equal source.turn_index'))
        if isinstance(start, (int, float)) and isinstance(source.get('target_start'), (int, float)) and abs(start - source['target_start']) > 1e-6:
            issues.append(issue('error', 'target_start_mismatch', '$.target_reply.start', 'target_reply.start must equal source.target_start'))
        if isinstance(end, (int, float)) and isinstance(source.get('target_end'), (int, float)) and abs(end - source['target_end']) > 1e-6:
            issues.append(issue('error', 'target_end_mismatch', '$.target_reply.end', 'target_reply.end must equal source.target_end'))

    elif record_type == 'style_label':
        evidence = record.get('evidence', [])
        if not evidence:
            issues.append(issue('warning', 'missing_evidence', '$.evidence', 'style_label should preferably include at least one evidence item'))
        labels = record.get('labels', {})
        if isinstance(labels, dict) and labels.get('style_tone_primary') in labels.get('style_tone_secondary', []):
            issues.append(issue('warning', 'duplicate_primary_secondary_style', '$.labels', 'primary style_tone should not repeat in secondary'))

    elif record_type == 'preference_pair':
        context = record.get('context', [])
        issues.extend(check_turn_sequence(context, '$.context'))
        if context and context[-1].get('role') != 'user':
            issues.append(issue('error', 'context_must_end_with_user', '$.context', 'preference context should end with a user turn'))
        chosen = record.get('chosen_reply', {})
        rejected = record.get('rejected_reply', {})
        if chosen.get('candidate_id') == rejected.get('candidate_id'):
            issues.append(issue('error', 'duplicate_candidate_id', '$', 'chosen_reply and rejected_reply must use different candidate_id'))
        if chosen.get('text') == rejected.get('text'):
            issues.append(issue('error', 'duplicate_candidate_text', '$', 'chosen_reply.text and rejected_reply.text must differ'))

    elif record_type == 'benchmark_case':
        messages = record.get('messages', [])
        prev_idx = -1
        for i, msg in enumerate(messages):
            t_idx = msg.get('turn_index')
            if t_idx != i:
                issues.append(issue('error', 'message_turn_index_not_sequential', f'$.messages[{i}].turn_index', f'expected {i}, got {t_idx}'))
            if i and t_idx <= prev_idx:
                issues.append(issue('error', 'message_turn_index_not_increasing', f'$.messages[{i}].turn_index', 'message turn_index must increase'))
            prev_idx = t_idx
        category = record.get('category')
        if category == 'multi_turn_followup' and len(messages) < 3:
            issues.append(issue('warning', 'too_few_messages_for_multiturn', '$.messages', 'multi_turn_followup should normally include at least 3 messages'))

    return issues


def cross_record_checks(records: list[dict[str, Any]]) -> None:
    id_seen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    style_label_ids = set()
    turn_sample_ids = set()

    for r in records:
        if r['parse_status'] != 'ok':
            continue
        obj = r['record']
        record_type = obj.get('record_type')
        id_key = ID_KEY_BY_RECORD_TYPE.get(record_type)
        if id_key and isinstance(obj.get(id_key), str):
            id_seen.setdefault((record_type, obj[id_key]), []).append(r)
        if record_type == 'style_label' and isinstance(obj.get('label_id'), str):
            style_label_ids.add(obj['label_id'])
        if record_type == 'turn_sft' and isinstance(obj.get('sample_id'), str):
            turn_sample_ids.add(obj['sample_id'])

    for (record_type, rid), rows in id_seen.items():
        if len(rows) > 1:
            for row in rows:
                row['issues'].append(issue('error', 'duplicate_record_id', '$', f'duplicate {record_type} id: {rid}'))

    for row in records:
        if row['parse_status'] != 'ok':
            continue
        obj = row['record']
        record_type = obj.get('record_type')
        if record_type == 'turn_sft':
            style_label_id = (((obj.get('meta') or {}).get('style_label_id')) or '').strip()
            if style_label_id and style_label_id not in style_label_ids:
                row['issues'].append(issue('warning', 'missing_style_label_reference', '$.meta.style_label_id', f'referenced style_label_id not found: {style_label_id}'))
        elif record_type == 'preference_pair':
            source_turn_sample_id = (((obj.get('source') or {}).get('source_turn_sample_id')) or '').strip()
            if source_turn_sample_id and source_turn_sample_id not in turn_sample_ids:
                row['issues'].append(issue('error', 'missing_turn_sample_reference', '$.source.source_turn_sample_id', f'referenced turn sample not found: {source_turn_sample_id}'))


def finalize_status(row: dict[str, Any]) -> None:
    issues: list[Issue] = row['issues']
    has_errors = any(i.severity == 'error' for i in issues)
    has_warnings = any(i.severity == 'warning' for i in issues)
    row['schema_valid'] = not any(i.code == 'schema_validation_error' for i in issues)
    row['qc_status'] = 'fail' if has_errors else ('warn' if has_warnings else 'pass')


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {
        'total_records': len(rows),
        'parse_fail': 0,
        'schema_valid': 0,
        'schema_invalid': 0,
        'qc_status_counts': Counter(),
        'record_type_counts': Counter(),
        'issue_code_counts': Counter(),
        'severity_counts': Counter(),
        'invalid_examples': [],
    }
    for row in rows:
        out['qc_status_counts'][row['qc_status']] += 1
        if row['parse_status'] != 'ok':
            out['parse_fail'] += 1
        if row.get('record_type'):
            out['record_type_counts'][row['record_type']] += 1
        if row['schema_valid']:
            out['schema_valid'] += 1
        else:
            out['schema_invalid'] += 1
        for i in row['issues']:
            out['issue_code_counts'][i.code] += 1
            out['severity_counts'][i.severity] += 1
        if row['qc_status'] == 'fail' and len(out['invalid_examples']) < 50:
            out['invalid_examples'].append({
                'source': row['source'],
                'record_type': row.get('record_type'),
                'first_issues': [i.to_dict() for i in row['issues'][:5]],
            })
    for k in ('qc_status_counts', 'record_type_counts', 'issue_code_counts', 'severity_counts'):
        out[k] = dict(out[k].most_common())
    return out


def main() -> None:
    args = parse_args()
    validators = load_validators(args.schema_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for path in iter_input_files(args.input_dir, args.include_glob, args.exclude_glob):
        rel = path.relative_to(args.input_dir).as_posix()
        try:
            raw_records = list(iter_records_from_file(path))
        except Exception as exc:
            rows.append({
                'source': rel,
                'line_no': None,
                'parse_status': 'load_error',
                'record_type': None,
                'schema_valid': False,
                'qc_status': 'fail',
                'issues': [issue('error', 'json_load_error', '$', str(exc))],
                'record': None,
            })
            continue

        for line_no, record in raw_records:
            row = {
                'source': rel,
                'line_no': line_no,
                'parse_status': 'ok',
                'record_type': record.get('record_type') if isinstance(record, dict) else None,
                'schema_valid': False,
                'qc_status': 'fail',
                'issues': [],
                'record': record,
            }
            if not isinstance(record, dict):
                row['issues'].append(issue('error', 'record_not_object', '$', f'record must be object, got {type(record).__name__}'))
                rows.append(row)
                continue

            record_type = record.get('record_type')
            if record_type not in validators:
                row['issues'].append(issue('error', 'unknown_record_type', '$.record_type', f'unsupported record_type: {record_type!r}'))
                rows.append(row)
                continue

            row['issues'].extend(validate_schema(record, validators[record_type]))
            row['issues'].extend(validate_record_semantics(record))
            rows.append(row)

    cross_record_checks(rows)
    for row in rows:
        finalize_status(row)

    summary = summarize(rows)

    records_out = args.out_dir / 'annotation_qc_records.jsonl'
    invalid_out = args.out_dir / 'annotation_qc_invalid.jsonl'
    summary_out = args.out_dir / 'annotation_qc_summary.json'

    with records_out.open('w', encoding='utf-8') as f_all, invalid_out.open('w', encoding='utf-8') as f_bad:
        for row in rows:
            payload = {
                'source': row['source'],
                'line_no': row['line_no'],
                'parse_status': row['parse_status'],
                'record_type': row['record_type'],
                'schema_valid': row['schema_valid'],
                'qc_status': row['qc_status'],
                'issues': [i.to_dict() for i in row['issues']],
            }
            f_all.write(json.dumps(payload, ensure_ascii=False) + '\n')
            if row['qc_status'] == 'fail':
                f_bad.write(json.dumps(payload, ensure_ascii=False) + '\n')

    summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
