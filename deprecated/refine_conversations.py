#!/usr/bin/env python3
"""
Refine the extracted conversations by manually reviewing and fixing boundaries.
"""

import json
import os
import re

def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HHMMSS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}{minutes:02d}{secs:02d}"

def load_json(file_path: str):
    """Load JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path: str, data):
    """Save JSON file."""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def merge_consecutive_speaker_segments(segments):
    """Merge consecutive segments from the same speaker."""
    if not segments:
        return []

    merged = []
    current = segments[0].copy()

    for seg in segments[1:]:
        # If same speaker and close in time (within 5 seconds), merge
        if seg['speaker'] == current['speaker'] and seg['start'] - current['end'] < 5:
            current['text'] += ' ' + seg['text']
            current['end'] = seg['end']
        else:
            merged.append(current)
            current = seg.copy()

    merged.append(current)
    return merged

def extract_better_tag(segments):
    """Extract a better tag from the conversation."""
    # Combine first 20 segments to get more context
    intro_text = ' '.join([seg['text'] for seg in segments[:20]])

    # Extract age
    age_match = re.search(r'(\d{2})岁', intro_text)
    age = age_match.group(1) if age_match else None

    # Extract education
    education = None
    if '博士' in intro_text:
        education = '博士'
    elif '硕士' in intro_text:
        education = '硕士'
    elif '本科' in intro_text:
        education = '本科'

    # Extract profession/industry
    profession = None
    professions = {
        '医生': '医生', '医学': '医学',
        '工程师': '工程师', '程序员': '程序员',
        '教师': '教师', '老师': '老师',
        '律师': '律师',
        '设计师': '设计师',
        '产品': '产品',
        '运营': '运营',
        '销售': '销售',
        '创业': '创业',
        '金融': '金融',
        '咨询': '咨询',
        '主播': '主播',
        '瑜伽': '瑜伽',
        '体制内': '体制内',
        '经纪': '经纪',
    }

    for key, value in professions.items():
        if key in intro_text:
            profession = value
            break

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(f"{age}岁")
    if education:
        tag_parts.append(education)
    if profession:
        tag_parts.append(profession)

    if not tag_parts:
        tag_parts.append('观众')

    return '_'.join(tag_parts)

def main():
    # Load original data
    input_file = "/home/duino/ws/ququ/process_youtube/06_downloads_json/曲曲2025（全）/07 - 曲曲現場直播 2025年1月23日 ｜ 曲曲麥肯錫.json"
    data = load_json(input_file)
    segments = data['segments']

    # Define manual conversation boundaries based on analysis
    # Format: (start_time, end_time, description)
    conversations = [
        # Conversation 1: 37岁博士创业 - Fixed boundary
        (705, 1146, "37岁博士创业"),
        # Conversation 2: 30岁经纪公司
        (1723, 2019, "30岁经纪公司"),
        # Conversation 3: 29岁主播
        (3360, 6317, "29岁主播"),
        # Conversation 4: 瑜伽老师
        (7197, 7473, "瑜伽老师"),
        # Conversation 5: 客户招商会
        (7585, 8322, "客户"),
        # Conversation 6: 32岁高校老师
        (8625, 9349, "32岁高校老师"),
        # Conversation 7: 24岁博士
        (13296, 13644, "24岁博士"),
        # Conversation 8: 23岁本科
        (19141, 19247, "23岁本科"),
        # Conversation 9: 34岁博士
        (20702, 21002, "34岁博士"),
    ]

    output_dir = "/home/duino/ws/ququ/process_youtube/07_conversations"
    date_dir = os.path.join(output_dir, "20250123")

    # Process each conversation
    for start_time, end_time, description in conversations:
        # Find segments in this time range
        conv_segments = [seg for seg in segments if start_time <= seg['start'] <= end_time]

        if not conv_segments:
            print(f"Warning: No segments found for {description} ({start_time}-{end_time})")
            continue

        # Merge consecutive speaker segments
        merged_segments = merge_consecutive_speaker_segments(conv_segments)

        # Extract better tag
        guest_tag = extract_better_tag(merged_segments)

        # Get timestamps
        start_ts = seconds_to_timestamp(merged_segments[0]['start'])
        end_ts = seconds_to_timestamp(merged_segments[-1]['end'])

        # Create filename
        filename = f"2025年1月23日_{start_ts}_{end_ts}_{guest_tag}.json"
        filepath = os.path.join(date_dir, filename)

        # Save
        output_data = {
            'metadata': {
                'source_file': os.path.basename(input_file),
                'date': '2025年1月23日',
                'start_time': start_ts,
                'end_time': end_ts,
                'guest_tag': guest_tag,
                'segment_count': len(merged_segments),
                'description': description
            },
            'segments': merged_segments
        }

        save_json(filepath, output_data)
        print(f"Saved: {filename}")
        print(f"  Segments: {len(merged_segments)}")
        print(f"  First text: {merged_segments[0]['text'][:80]}")
        print()

if __name__ == "__main__":
    main()
