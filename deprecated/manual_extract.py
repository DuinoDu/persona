#!/usr/bin/env python3
"""
Extract conversations with better boundary detection.
"""

import json
import os
import re

def load_json_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}{minutes:02d}{secs:02d}"

def merge_consecutive_segments(segments):
    if not segments:
        return []

    merged = []
    current = {
        'start': segments[0]['start'],
        'end': segments[0]['end'],
        'speaker': segments[0]['speaker'],
        'text': segments[0]['text']
    }

    for seg in segments[1:]:
        if seg['speaker'] == current['speaker'] and seg['start'] - current['end'] < 5:
            current['end'] = seg['end']
            current['text'] += seg['text']
        else:
            if current['text'].strip():
                merged.append(current)
            current = {
                'start': seg['start'],
                'end': seg['end'],
                'speaker': seg['speaker'],
                'text': seg['text']
            }

    if current['text'].strip():
        merged.append(current)

    return merged

def extract_tag_from_intro(text):
    """Extract audience tag from introduction text."""
    # Look for age
    age_match = re.search(r'(\d{2})岁', text)
    age = age_match.group(1) if age_match else None

    # Look for occupation/description keywords
    keywords = []

    if '博士' in text:
        keywords.append('博士')
    elif '硕士' in text:
        keywords.append('硕士')
    elif '本科' in text:
        keywords.append('本科')

    if '医生' in text or '医学' in text:
        keywords.append('医生')
    if '律师' in text:
        keywords.append('律师')
    if '教师' in text or '老师' in text:
        keywords.append('教师')
    if '程序员' in text or '码农' in text:
        keywords.append('程序员')
    if '公务员' in text or '体制内' in text:
        keywords.append('体制内')
    if '航空' in text:
        keywords.append('航空')
    if '单亲妈妈' in text:
        keywords.append('单亲妈妈')
    if '美国' in text or '美利国' in text:
        keywords.append('美国')
    if '主播' in text:
        keywords.append('主播')
    if '表演' in text or '播音' in text:
        keywords.append('艺术')

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(f"{age}岁")
    tag_parts.extend(keywords[:2])  # Max 2 keywords

    if not tag_parts:
        return "观众"

    return "".join(tag_parts)

def main():
    input_file = "06_downloads_json/曲曲2025（全）/20 - 曲曲現場直播 2025年3月21日 ｜ 曲曲麥肯錫.json"
    output_dir = "07_conversations/曲曲2025（全）/20250321"

    print(f"Loading {input_file}...")
    data = load_json_file(input_file)
    segments = data['segments']

    merged = merge_consecutive_segments(segments)
    print(f"Merged segments: {len(merged)}")

    # Manually identified conversations based on analysis
    # Format: (start_time_seconds, end_time_seconds, guest_speaker, intro_text)
    conversations = [
        (834, 2252, "SPEAKER_00", "43岁美国航空公司单亲妈妈"),
        (2909, 5954, "SPEAKER_03", "观众"),
        (10336, 15956, "SPEAKER_00", "29岁女生"),
        (20000, 22842, "SPEAKER_00", "观众"),
        (22845, 24742, "SPEAKER_03", "99年艺术教育培训"),
        (24749, 25953, "SPEAKER_03", "28岁主播"),
        (25959, 32502, "SPEAKER_00", "观众"),
    ]

    # Let me print segments around key timestamps to manually identify conversations
    print("\nAnalyzing key segments...")

    # Print segments every 10 minutes
    for time_sec in range(0, int(merged[-1]['end']), 600):
        # Find segment at this time
        for seg in merged:
            if seg['start'] <= time_sec <= seg['end']:
                print(f"\n[{format_timestamp(time_sec)}] {seg['speaker']}: {seg['text'][:100]}")
                break

if __name__ == "__main__":
    main()
