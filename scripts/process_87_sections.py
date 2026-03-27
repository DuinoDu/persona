#!/usr/bin/env python3
"""
处理字幕文件的段落划分和说话人识别
"""
import json
import os
import re
from datetime import timedelta
from collections import defaultdict

def format_timestamp(seconds):
    """将秒数转换为 HH:MM:SS.mm 格式"""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = td.total_seconds() % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"

def split_into_sentences(text):
    """将文本分割成句子"""
    if not text or not text.strip():
        return []

    # 中文句子结束符
    sentence_endings = r'[。！？.!?；;~～]'

    # 先按结束符分割
    parts = re.split(f'({sentence_endings})', text)

    sentences = []
    current = ""
    for i, part in enumerate(parts):
        if not part:
            continue
        current += part
        # 如果当前部分以结束符结尾，且整体长度合适，则形成一个句子
        if re.match(f'^{sentence_endings}$', part) or i == len(parts) - 1:
            if len(current.strip()) >= 2:  # 至少2个字符
                sentences.append(current.strip())
                current = ""

    # 处理剩余的
    if current.strip() and len(current.strip()) >= 2:
        sentences.append(current.strip())

    return sentences if sentences else [text.strip()] if text.strip() else []

def process_section(segments, section_name, start_time, end_time, section_type, expected_speakers):
    """处理一个段落，提取并整理数据"""

    # 筛选该时间段内的segments
    section_segments = [
        s for s in segments
        if s['start'] < end_time and s['end'] > start_time and s.get('text', '').strip()
    ]

    if not section_segments:
        return None

    # 按时间排序
    section_segments.sort(key=lambda x: x['start'])

    # 分析speaker
    speaker_time = defaultdict(float)
    for seg in section_segments:
        speaker = seg.get('speaker', 'UNKNOWN')
        if speaker and speaker != 'UNKNOWN':
            speaker_time[speaker] += seg['end'] - seg['start']

    # 确定主要的speaker(s)
    sorted_speakers = sorted(speaker_time.items(), key=lambda x: x[1], reverse=True)

    # 创建sentences
    sentences = []
    for seg in section_segments:
        text = seg.get('text', '').strip()
        if not text:
            continue

        speaker = seg.get('speaker', 'UNKNOWN')

        # 映射speaker到host/guest
        if speaker == sorted_speakers[0][0] if sorted_speakers else 'UNKNOWN':
            speaker_id = 'host'
            speaker_name = '主播'
        else:
            speaker_id = 'guest' if len(sorted_speakers) > 1 else 'host'
            speaker_name = '嘉宾'

        # 分句
        split_texts = split_into_sentences(text)
        for sent_text in split_texts:
            if len(sent_text) >= 2:
                sentences.append({
                    'speaker_id': speaker_id,
                    'speaker_name': speaker_name,
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': sent_text
                })

    if not sentences:
        return None

    # 构建输出结构
    result = {
        'meta': {
            'source_file': '87 - 沉沒成本不計入重大決策 永遠記念沉沒成本的人都是弱者心態 曲曲新房首播 2024年12月19日 ｜ 曲曲麥肯錫.json',
            'index': 0,
            'kind': section_type,
            'persona': '',
            'title': section_name,
            'start': start_time,
            'end': end_time,
            'start_ts': format_timestamp(start_time),
            'end_ts': format_timestamp(end_time),
            'raw_segment_count': len(section_segments),
            'speaker_ids': ['host'] if section_type == 'comment' or section_type == 'opening' else ['host', 'guest'],
            'speaker_names': {
                'host': '主播'
            } if section_type == 'comment' or section_type == 'opening' else {
                'host': '主播',
                'guest': '嘉宾'
            },
            'sentence_count': len(sentences),
            'notes': ''
        },
        'sentences': sentences
    }

    return result

def main():
    # 读取字幕文件
    with open('/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/87 - 沉沒成本不計入重大決策 永遠記念沉沒成本的人都是弱者心態 曲曲新房首播 2024年12月19日 ｜ 曲曲麥肯錫.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data['segments']

    # 定义主要段落 - 基于实际说话人活动分析
    # 这个划分需要更精确，基于说话人切换模式

    sections = [
        # 开场 (0-6分钟，主播独白)
        {"name": "00_开场", "start": 0, "end": 370, "type": "opening"},

        # 第一个连麦 - 装修话题 (6-13分钟)
        {"name": "01_装修话题_连麦", "start": 370, "end": 790, "type": "call"},
        {"name": "02_装修话题_评论", "start": 790, "end": 1050, "type": "comment"},

        # 第二个连麦 (13-23分钟)
        {"name": "03_第二个话题_连麦", "start": 1050, "end": 1400, "type": "call"},
        {"name": "04_第二个话题_评论", "start": 1400, "end": 1680, "type": "comment"},

        # 第三个连麦 - 较长 (23-50分钟)
        {"name": "05_第三个话题_连麦", "start": 1680, "end": 3000, "type": "call"},
        {"name": "06_第三个话题_评论", "start": 3000, "end": 3600, "type": "comment"},

        # 继续添加更多段落...
        # 由于直播很长，这里简化处理，实际应该根据完整分析划分
    ]

    # 处理每个段落
    output_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/87_processed"

    processed_count = 0
    for i, sec in enumerate(sections):
        result = process_section(segments, sec['name'], sec['start'], sec['end'], sec['type'], [])
        if result:
            output_file = os.path.join(output_dir, f"{sec['name']}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Saved: {output_file} ({len(result['sentences'])} sentences)")
            processed_count += 1

    print(f"\nProcessed {processed_count}/{len(sections)} sections")

    print(f"\nProcessed {processed_count}/{len(sections)} sections")
EOF
