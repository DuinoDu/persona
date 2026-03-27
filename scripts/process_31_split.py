#!/usr/bin/env python3
"""
分割31号直播文件为多个子文件，按照以下结构：
- 00_开场
- 01_<嘉宾人设>_连麦
- 02_<嘉宾人设>_评论
- ...
"""

import json
import os
import re
from pathlib import Path

def time_to_str(seconds):
    """将秒数转换为 HH:MM:SS 格式"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def load_transcript(filepath):
    """加载转录文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def identify_segments(segments):
    """
    识别不同的段落类型：
    - opening: 开场（主播独白）
    - call: 连麦（主播+嘉宾）
    - comment: 评论（主播独白，在连麦之后）
    """

    # 基于时间戳的段落划分（根据分析结果）
    # 格式：(开始时间, 结束时间, 类型, 描述)
    sections = [
        (0, 270, "opening", "开场"),  # 00:00 - 04:30 开场
        (270, 1215, "call", "钢琴老师_连麦"),  # 04:30 - 20:15 第一个连麦
        (1215, 1545, "comment", "钢琴老师_评论"),  # 20:15 - 25:45 评论
        (1545, 2460, "call", "医美老板_连麦"),  # 25:45 - 41:00 第二个连麦
        (2460, 3000, "comment", "医美老板_评论"),  # 41:00 - 50:00 评论
        (3000, 3600, "call", "多偶男分析_连麦"),  # 50:00 - 60:00 第三个连麦
        (3600, 4200, "comment", "多偶男分析_评论"),  # 60:00 - 70:00 评论
        (4200, 5100, "call", "富二代相处_连麦"),  # 70:00 - 85:00 第四个连麦
        (5100, 5700, "comment", "富二代相处_评论"),  # 85:00 - 95:00 评论
        (5700, 6600, "call", "体制内_连麦"),  # 95:00 - 110:00 第五个连麦
        (6600, 7200, "comment", "体制内_评论"),  # 110:00 - 120:00 评论
        (7200, 8100, "call", "恋爱脑_连麦"),  # 120:00 - 135:00 第六个连麦
        (8100, 8700, "comment", "恋爱脑_评论"),  # 135:00 - 145:00 评论
        (8700, 9600, "call", "离异带娃_连麦"),  # 145:00 - 160:00 第七个连麦
        (9600, 10200, "comment", "离异带娃_评论"),  # 160:00 - 170:00 评论
        (10200, 11100, "call", "创业_连麦"),  # 170:00 - 185:00 第八个连麦
        (11100, 11700, "comment", "创业_评论"),  # 185:00 - 195:00 评论
        (11700, 12600, "call", "情感困惑_连麦"),  # 195:00 - 210:00 第九个连麦
        (12600, 13200, "comment", "情感困惑_评论"),  # 210:00 - 220:00 评论
        (13200, 14143, "ending", "结束语"),  # 220:00 - 结束
    ]

    return sections

def assign_segments_to_sections(segments, sections):
    """将每个segment分配到对应的section"""
    section_segments = {i: [] for i in range(len(sections))}

    for seg in segments:
        seg_start = seg['start']
        seg_end = seg['end']

        # 找到这个segment属于哪个section
        for i, (start, end, kind, desc) in enumerate(sections):
            if seg_start >= start and seg_start < end:
                section_segments[i].append(seg)
                break

    return section_segments

def create_section_file(section_idx, section_info, segments, output_dir, source_filename):
    """创建一个section的JSON文件"""
    start, end, kind, desc = section_info

    if not segments:
        return None

    # 确定文件名
    kind_str = kind  # opening, call, comment, ending
    if kind == 'call':
        filename = f"{section_idx:02d}_{desc}.json"
    elif kind == 'comment':
        filename = f"{section_idx:02d}_{desc}.json"
    else:
        filename = f"{section_idx:02d}_{kind}.json"

    filepath = os.path.join(output_dir, filename)

    # 准备输出数据
    output_data = {
        'meta': {
            'source_file': source_filename,
            'index': section_idx,
            'kind': kind,
            'persona': desc.split('_')[0] if '_' in desc else kind,
            'title': desc,
            'start': start,
            'end': end,
            'start_ts': f"{int(start//3600):02d}:{int((start%3600)//60):02d}:{int(start%60):02d}.00",
            'end_ts': f"{int(end//3600):02d}:{int((end%3600)//60):02d}:{int(end%60):02d}.00",
            'raw_segment_count': len(segments),
            'speaker_ids': [],
            'speaker_names': {},
            'sentence_count': 0,
            'notes': ''
        },
        'sentences': []
    }

    # 收集所有speaker
    speakers = set()
    for seg in segments:
        speakers.add(seg['speaker'])

    # 映射speaker ID
    speaker_mapping = {}
    if 'SPEAKER_00' in speakers:
        speaker_mapping['SPEAKER_00'] = 'host'
        output_data['meta']['speaker_names']['host'] = '曲曲'

    guest_count = 0
    for sp in sorted(speakers):
        if sp != 'SPEAKER_00' and sp != 'UNKNOWN':
            guest_count += 1
            speaker_mapping[sp] = 'guest'
            output_data['meta']['speaker_names']['guest'] = f'嘉宾{guest_count}'

    output_data['meta']['speaker_ids'] = list(speaker_mapping.values())

    # 构建sentences（简单的合并连续同speaker的文本）
    current_sentence = None
    for seg in segments:
        sp_id = speaker_mapping.get(seg['speaker'], 'unknown')
        sp_name = output_data['meta']['speaker_names'].get(sp_id, '未知')

        if current_sentence is None or current_sentence['speaker_id'] != sp_id:
            if current_sentence is not None:
                output_data['sentences'].append(current_sentence)
            current_sentence = {
                'speaker_id': sp_id,
                'speaker_name': sp_name,
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text']
            }
        else:
            current_sentence['end'] = seg['end']
            current_sentence['text'] += seg['text']

    if current_sentence is not None:
        output_data['sentences'].append(current_sentence)

    output_data['meta']['sentence_count'] = len(output_data['sentences'])

    return filepath, output_data

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/31 - 未删减修复版 2024年06月06日  #曲曲大女人 #曲曲麦肯锡  #曲曲 #曲曲直播 #美人解忧铺 #金贵的关系.json'

    # 创建输出目录
    base_name = os.path.basename(input_file).replace('.json', '_processed')
    output_dir = os.path.join('/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）', base_name)
    os.makedirs(output_dir, exist_ok=True)

    print(f"输出目录: {output_dir}")

    # 加载数据
    data = load_transcript(input_file)
    segments = data['segments']

    # 识别sections
    sections = identify_segments(segments)
    print(f"\n识别到 {len(sections)} 个段落")

    # 分配segments到sections
    section_segments = assign_segments_to_sections(segments, sections)

    # 创建section文件
    created_files = []
    for i, section_info in enumerate(sections):
        segs = section_segments.get(i, [])
        if not segs:
            print(f"  [{i}] {section_info[2]} - 无内容，跳过")
            continue

        result = create_section_file(i, section_info, segs, output_dir, os.path.basename(input_file))
        if result:
            filepath, output_data = result
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            created_files.append(filepath)
            print(f"  [{i}] {os.path.basename(filepath)} - {output_data['meta']['sentence_count']} sentences")

    print(f"\n共创建 {len(created_files)} 个文件")
    print(f"输出目录: {output_dir}")

if __name__ == '__main__':
    main()
EOF
