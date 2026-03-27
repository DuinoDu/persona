#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_META = ROOT / 'data/ququ_meta.json'
DEFAULT_OUT_DIR = ROOT / 'data/05_annotations/sft_v1'

TOPIC_KEYWORDS = [
    ('marriage', ['结婚', '婚姻', '订婚', '离婚', '复婚', '婚检', '催婚', '领证', '围城']),
    ('relationship', ['恋爱', '男友', '女友', '对象', '分手', '复联', '暧昧', '追求', '相亲', '感情', '关系', '择偶']),
    ('career', ['工作', '职业', '上班', '晋升', '转行', '创业', '事业', '职场', '岗位', '老板', '公司', 'offer', '实习']),
    ('money', ['钱', '收入', '存款', '彩礼', '房', '车', '资产', '负债', '礼物', '花钱', '米', '工资', '财务']),
    ('family', ['父母', '妈妈', '爸爸', '婆婆', '公婆', '家里', '家庭', '孩子', '娃', '原生家庭']),
    ('education', ['本科', '硕士', '博士', '读书', '学校', '留学', '考研', '高考', '学历', '老师']),
    ('health', ['生病', '抑郁', '焦虑症', '怀孕', '流产', '身体', '健康', '手术']),
    ('social', ['朋友', '社交', '圈子', '人脉', '同学', '同事']),
    ('emotion', ['情绪', '难受', '崩溃', '痛苦', '内耗', '不开心', '焦虑', '委屈']),
    ('self_growth', ['成长', '提升', '自信', '自卑', '改变', '规划', '目标', '人生']),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Generate initial conversation_v1.jsonl and bad call cases from ququ parts meta.')
    p.add_argument('--meta', type=Path, default=DEFAULT_META)
    p.add_argument('--out-dir', type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument('--conversation-name', default='conversation_v1.jsonl')
    p.add_argument('--bad-cases-name', default='bad_call_cases_v1.jsonl')
    p.add_argument('--summary-name', default='conversation_v1_summary.json')
    p.add_argument('--min-turns', type=int, default=2)
    p.add_argument('--default-train-split', default='train', choices=['train', 'dev', 'test', 'holdout'])
    p.add_argument('--annotator-id', default='assistant_bootstrap')
    return p.parse_args()


def extract_year_digits(value: str) -> str:
    m = re.search(r'(20\d{2})', value)
    return m.group(1) if m else 'unknown'


def infer_topic_primary(*texts: str) -> str:
    merged = ' '.join(t for t in texts if t)
    for topic, keywords in TOPIC_KEYWORDS:
        if any(k in merged for k in keywords):
            return topic
    return 'other'


def normalize_text(text: str) -> str:
    text = (text or '').strip()
    text = re.sub(r'\s+', ' ', text)
    return text


@dataclass
class MergeResult:
    turns: list[dict[str, Any]]
    overlap_count: int



def merge_sentences_to_turns(sentences: list[dict[str, Any]], section_file: str) -> MergeResult:
    turns: list[dict[str, Any]] = []
    overlap_count = 0
    prev_end: float | None = None

    for idx, sent in enumerate(sentences):
        speaker_id = sent.get('speaker_id')
        if speaker_id not in {'host', 'guest'}:
            continue
        text = normalize_text(sent.get('text', ''))
        if turns and turns[-1]['speaker_id'] == speaker_id:
            turns[-1]['text_parts'].append(text)
            turns[-1]['end'] = max(turns[-1]['end'], sent['end'])
            turns[-1]['sentence_end_idx'] = idx
        else:
            turns.append({
                'speaker_id': speaker_id,
                'speaker_name': sent.get('speaker_name') or ('曲曲' if speaker_id == 'host' else '嘉宾'),
                'start': sent['start'],
                'end': sent['end'],
                'text_parts': [text],
                'section_file': section_file,
                'sentence_start_idx': idx,
                'sentence_end_idx': idx,
            })

    finalized: list[dict[str, Any]] = []
    for turn_idx, turn in enumerate(turns):
        start = turn['start']
        if prev_end is not None and start < prev_end:
            overlap_count += 1
            start = prev_end
        end = max(start, turn['end'])
        role = 'persona' if turn['speaker_id'] == 'host' else 'user'
        finalized.append({
            'turn_index': turn_idx,
            'role': role,
            'speaker_id': turn['speaker_id'],
            'speaker_name': turn['speaker_name'],
            'start': round(float(start), 6),
            'end': round(float(end), 6),
            'text': normalize_text(' '.join(p for p in turn['text_parts'] if p)),
            'section_file': turn['section_file'],
            'sentence_start_idx': turn['sentence_start_idx'],
            'sentence_end_idx': turn['sentence_end_idx'],
        })
        prev_end = end
    return MergeResult(turns=finalized, overlap_count=overlap_count)



def build_conversation_record(year_label: str, record: dict[str, Any], part: dict[str, Any], part_obj: dict[str, Any], turns: list[dict[str, Any]], *, default_train_split: str, annotator_id: str, created_at: str) -> dict[str, Any]:
    episode_no = int(record.get('episode_no') or part.get('episode_no') or 0)
    year_digits = extract_year_digits(year_label)
    part_index = int(part['index'])
    transcript = record.get('transcript') or {}
    episode_title = transcript.get('stem') or record.get('download', {}).get('stem') or record.get('id')
    section_file = f"data/{part['path']}"
    section_hash = hashlib.sha1(section_file.encode('utf-8')).hexdigest()[:8]
    topic_primary = infer_topic_primary(part.get('persona', ''), part.get('title', ''), episode_title)
    transcript_quality = 'B'

    return {
        'record_type': 'conversation',
        'version': 'annotation_v1',
        'conversation_id': f'conv_{year_digits}_{episode_no:03d}_{part_index:03d}_{section_hash}',
        'source': {
            'project': 'ququ_youtube',
            'year': year_label,
            'episode_id': f'{year_digits}_{episode_no:03d}',
            'episode_title': episode_title,
            'raw_source_file': part_obj.get('meta', {}).get('source_file') or transcript.get('file') or '',
            'language': 'zh',
            'persona_name': '曲曲',
            'section_file': section_file,
            'section_index': part_index,
            'section_kind': 'call',
            'persona': part.get('persona', ''),
            'start': part.get('start'),
            'end': part.get('end'),
        },
        'turns': turns,
        'meta': {
            'topic_primary': topic_primary,
            'topic_secondary': [],
            'guest_persona': part.get('persona', ''),
            'transcript_quality': transcript_quality,
            'train_split': default_train_split,
            'safety_flags': [],
            'notes': 'auto_bootstrap_v1: generated from call part after speaker/turn filtering; train_split is placeholder.',
        },
        'audit': {
            'annotation_status': 'draft',
            'annotator_id': annotator_id,
            'created_at': created_at,
            'updated_at': created_at,
        },
    }



def main() -> None:
    args = parse_args()
    meta = json.loads(args.meta.read_text(encoding='utf-8'))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    conv_path = args.out_dir / args.conversation_name
    bad_path = args.out_dir / args.bad_cases_name
    summary_path = args.out_dir / args.summary_name

    created_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

    conversation_records: list[dict[str, Any]] = []
    bad_cases: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        'generated_at': created_at,
        'source_meta': str(args.meta.relative_to(ROOT)),
        'min_turns': args.min_turns,
        'default_train_split': args.default_train_split,
        'conversation_count': 0,
        'bad_case_count': 0,
        'by_year': defaultdict(lambda: Counter()),
        'bad_reason_counts': Counter(),
        'topic_primary_counts': Counter(),
    }

    for year in meta.get('years', []):
        year_label = year['year']
        for record in year.get('records', []):
            for parts_dir in record.get('parts_dirs', []):
                for part in parts_dir.get('parts', []):
                    if part.get('kind') != 'call':
                        continue
                    file_path = ROOT / 'data' / part['path']
                    part_obj = json.loads(file_path.read_text(encoding='utf-8'))
                    sentences = [s for s in part_obj.get('sentences', []) if isinstance(s, dict)]
                    sentence_speakers = [s.get('speaker_id') for s in sentences]
                    counts = Counter(sentence_speakers)
                    merge = merge_sentences_to_turns(sentences, f"data/{part['path']}")
                    turns = merge.turns

                    reasons: list[str] = []
                    if not sentences:
                        reasons.append('empty_sentences')
                    if counts.get('host', 0) == 0:
                        reasons.append('no_host_sentences')
                    if counts.get('guest', 0) == 0:
                        reasons.append('no_guest_sentences')
                    if any(sp not in {'host', 'guest'} for sp in sentence_speakers if sp is not None):
                        reasons.append('unexpected_speaker_id')
                    if len(turns) < args.min_turns:
                        reasons.append(f'turn_count_lt_{args.min_turns}')
                    if not any(t['role'] == 'persona' and i > 0 and turns[i - 1]['role'] == 'user' for i, t in enumerate(turns)):
                        reasons.append('no_targetable_persona_turn')
                    if any(not t['text'] for t in turns):
                        reasons.append('empty_turn_text')

                    if reasons:
                        bad = {
                            'year': year_label,
                            'episode_id': f"{extract_year_digits(year_label)}_{int(record.get('episode_no') or 0):03d}",
                            'episode_title': (record.get('transcript') or {}).get('stem') or (record.get('download') or {}).get('stem') or record.get('id'),
                            'section_file': f"data/{part['path']}",
                            'section_index': part.get('index'),
                            'persona': part.get('persona'),
                            'start': part.get('start'),
                            'end': part.get('end'),
                            'reason_codes': reasons,
                            'sentence_count': len(sentences),
                            'merged_turn_count': len(turns),
                            'host_sentence_count': counts.get('host', 0),
                            'guest_sentence_count': counts.get('guest', 0),
                            'merged_role_sequence': [t['role'] for t in turns[:12]],
                            'preview_sentences': [
                                {
                                    'speaker_id': s.get('speaker_id'),
                                    'start': s.get('start'),
                                    'end': s.get('end'),
                                    'text': normalize_text(s.get('text', '')),
                                }
                                for s in sentences[:8]
                            ],
                        }
                        bad_cases.append(bad)
                        summary['by_year'][year_label]['bad_cases'] += 1
                        for reason in reasons:
                            summary['bad_reason_counts'][reason] += 1
                        continue

                    conv = build_conversation_record(
                        year_label,
                        record,
                        part,
                        part_obj,
                        turns,
                        default_train_split=args.default_train_split,
                        annotator_id=args.annotator_id,
                        created_at=created_at,
                    )
                    conversation_records.append(conv)
                    summary['by_year'][year_label]['conversations'] += 1
                    summary['by_year'][year_label]['persona_targetable_turns'] += sum(
                        1 for i, t in enumerate(turns) if t['role'] == 'persona' and i > 0 and turns[i - 1]['role'] == 'user'
                    )
                    summary['topic_primary_counts'][conv['meta']['topic_primary']] += 1

    with conv_path.open('w', encoding='utf-8') as fh:
        for rec in conversation_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    with bad_path.open('w', encoding='utf-8') as fh:
        for rec in bad_cases:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    summary['conversation_count'] = len(conversation_records)
    summary['bad_case_count'] = len(bad_cases)
    summary['by_year'] = {k: dict(v) for k, v in summary['by_year'].items()}
    summary['bad_reason_counts'] = dict(summary['bad_reason_counts'].most_common())
    summary['topic_primary_counts'] = dict(summary['topic_primary_counts'].most_common())
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'Wrote {conv_path}')
    print(f'Wrote {bad_path}')
    print(f'Wrote {summary_path}')


if __name__ == '__main__':
    main()
