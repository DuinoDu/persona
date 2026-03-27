#!/usr/bin/env python3
"""
Final comprehensive conversation extraction with manual boundary definitions.
Based on careful analysis of the live stream structure.
"""

import json
import os
import re

def load_json(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path: str, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HHMMSS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}{minutes:02d}{secs:02d}"

def merge_consecutive_segments(segments):
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

def extract_guest_tag(segments):
    """Extract guest tag from conversation."""
    # Combine first 20 segments
    intro_text = ' '.join([seg['text'] for seg in segments[:min(20, len(segments))]])

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

    # Extract profession/keywords
    keywords = []
    profession_map = {
        '医生': '医生', '医学': '医学',
        '工程师': '工程师', '程序员': '程序员',
        '教师': '教师', '老师': '老师', '高校': '高校老师',
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
        '博主': '博主',
    }

    for key, value in profession_map.items():
        if key in intro_text:
            keywords.append(value)
            break

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(f"{age}岁")
    if education:
        tag_parts.append(education)
    if keywords:
        tag_parts.extend(keywords[:1])  # Only take first keyword

    if not tag_parts:
        # Try to extract any identifying info
        if '女生' in intro_text or '女' in intro_text:
            tag_parts.append('女观众')
        else:
            tag_parts.append('观众')

    return '_'.join(tag_parts)

def process_conversation(segments, start_time, end_time, output_dir, date_str, date_original, source_file):
    """Process and save a single conversation."""
    # Extract segments in time range
    conv_segments = [seg for seg in segments if start_time <= seg['start'] <= end_time]

    if not conv_segments:
        print(f"Warning: No segments found for {start_time}-{end_time}")
        return None

    # Merge consecutive speaker segments
    merged_segments = merge_consecutive_segments(conv_segments)

    # Extract guest tag
    guest_tag = extract_guest_tag(merged_segments)

    # Get timestamps
    start_ts = seconds_to_timestamp(merged_segments[0]['start'])
    end_ts = seconds_to_timestamp(merged_segments[-1]['end'])

    # Create filename
    filename = f"{date_original}_{start_ts}_{end_ts}_{guest_tag}.json"
    filepath = os.path.join(output_dir, date_str, filename)

    # Save
    output_data = {
        'metadata': {
            'source_file': source_file,
            'date': date_original,
            'start_time': start_ts,
            'end_time': end_ts,
            'guest_tag': guest_tag,
            'segment_count': len(merged_segments)
        },
        'segments': merged_segments
    }

    save_json(filepath, output_data)

    print(f"Saved: {filename}")
    print(f"  Segments: {len(merged_segments)}")
    print(f"  First: {merged_segments[0]['text'][:60]}")
    print(f"  Last: {merged_segments[-1]['text'][:60]}")
    print()

    return filename


def identify_host(segments):
    """Identify the host speaker (most greeting phrases)."""
    from collections import defaultdict
    speaker_greetings = defaultdict(int)
    greeting_keywords = ['哈喽', '你好', '来下一个', '下一位', '拜拜', '欢迎', '谢谢']
    for seg in segments:
        speaker = seg['speaker']
        text = seg.get('text', '')
        for kw in greeting_keywords:
            speaker_greetings[speaker] += text.count(kw)
    if not speaker_greetings:
        return 'SPEAKER_00'
    return max(speaker_greetings, key=speaker_greetings.get)


def find_conversation_boundaries(segments, host):
    """
    Automatically identify conversation boundaries based on speaker patterns.
    Returns list of dicts with start_time, end_time, guest_speaker, segments.
    """
    conversations = []
    current_guest = None
    conv_start_time = None
    last_guest_end = None
    conv_segments = []

    for seg in segments:
        speaker = seg['speaker']
        if speaker == host or speaker == 'UNKNOWN':
            if current_guest and last_guest_end:
                if seg['start'] - last_guest_end > 120:
                    if conv_segments:
                        conversations.append({
                            'start_time': conv_start_time,
                            'end_time': last_guest_end + 30,
                            'guest_speaker': current_guest,
                            'segments': conv_segments,
                        })
                    current_guest = None
                    conv_start_time = None
                    last_guest_end = None
                    conv_segments = []
                else:
                    conv_segments.append(seg)
            continue

        if current_guest is None:
            current_guest = speaker
            conv_start_time = seg['start']
            last_guest_end = seg['end']
            conv_segments = [seg]
        elif speaker == current_guest:
            last_guest_end = seg['end']
            conv_segments.append(seg)
        else:
            if seg['start'] - last_guest_end > 60:
                if conv_segments:
                    conversations.append({
                        'start_time': conv_start_time,
                        'end_time': last_guest_end + 30,
                        'guest_speaker': current_guest,
                        'segments': conv_segments,
                    })
                current_guest = speaker
                conv_start_time = seg['start']
                last_guest_end = seg['end']
                conv_segments = [seg]
            else:
                conv_segments.append(seg)

    if conv_segments and current_guest:
        conversations.append({
            'start_time': conv_start_time,
            'end_time': conv_segments[-1].get('end', last_guest_end),
            'guest_speaker': current_guest,
            'segments': conv_segments,
        })

    # Filter out very short conversations (< 3 min)
    result = []
    for c in conversations:
        duration = c['end_time'] - c['start_time']
        if duration > 180:
            result.append(c)
    return result


def extract_date_from_filename(filename):
    """Extract date string and YYYYMMDD from filename."""
    match = re.search(r'(\d{4})\xe5\xb9\xb4(\d{1,2})\xe6\x9c\x88(\d{1,2})\xe6\x97\xa5', filename)
    if not match:
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', filename)
    if match:
        y, m, d = match.groups()
        return f"{y}年{int(m)}月{int(d)}日", f"{y}{int(m):02d}{int(d):02d}"
    return None, None


def process_single_transcript(input_file, output_base_dir):
    """Process a single transcript JSON -> extract conversations."""
    data = load_json(input_file)
    segments = data.get('segments', [])
    if not segments:
        print(f"  SKIP (no segments): {input_file}")
        return 0

    filename = os.path.basename(input_file)
    date_original, date_dir = extract_date_from_filename(filename)
    if not date_original:
        print(f"  SKIP (no date): {filename}")
        return 0

    output_dir = os.path.join(output_base_dir, date_dir)

    if os.path.isdir(output_dir) and len(os.listdir(output_dir)) > 0:
        print(f"  SKIP (exists): {output_dir}")
        return 0

    print(f"  Processing: {filename}")
    print(f"  Total segments: {len(segments)}")

    host = identify_host(segments)
    print(f"  Host: {host}")

    conversations = find_conversation_boundaries(segments, host)
    print(f"  Found {len(conversations)} conversations")

    if not conversations:
        return 0

    os.makedirs(output_dir, exist_ok=True)
    saved = 0

    for i, conv in enumerate(conversations, 1):
        start_time = conv['start_time']
        end_time = conv['end_time']

        conv_segments = []
        for s in segments:
            if start_time <= s['start'] <= end_time:
                conv_segments.append(s)
        if not conv_segments:
            continue

        merged = merge_consecutive_segments(conv_segments)
        guest_tag = extract_guest_tag(merged)

        start_ts = seconds_to_timestamp(start_time)
        end_ts = seconds_to_timestamp(end_time)

        output_data = {
            'conversation_id': i,
            'start_time': start_time,
            'end_time': end_time,
            'start_timestamp': start_ts,
            'end_timestamp': end_ts,
            'guest_tag': guest_tag,
            'host_speaker': host,
            'guest_speaker': conv['guest_speaker'],
            'segments': merged,
        }

        safe_tag = guest_tag.replace('/', '_').replace('\\', '_')
        out_filename = f"{date_original}_{start_ts}_{end_ts}_{safe_tag}.json"
        out_path = os.path.join(output_dir, out_filename)

        save_json(out_path, output_data)
        print(f"    [{i}] {out_filename}")
        saved += 1

    return saved


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Step 05: Extract individual conversations from transcript JSONs"
    )
    parser.add_argument("--input-dir", type=str, default="data/03_transcripts",
                        help="Input dir with merged transcript JSONs")
    parser.add_argument("--output-dir", type=str, default="data/04_conversations",
                        help="Output dir for conversation JSONs")
    parser.add_argument("--file", type=str, default=None,
                        help="Process a single file instead of entire directory")
    args = parser.parse_args()

    if args.file:
        count = process_single_transcript(args.file, args.output_dir)
        print(f"\nExtracted {count} conversations")
    else:
        total_files = 0
        total_convs = 0
        input_base = args.input_dir

        for root, dirs, files in os.walk(input_base):
            for f in sorted(files):
                if not f.endswith('.json'):
                    continue
                filepath = os.path.join(root, f)
                rel = os.path.relpath(root, input_base)
                out_dir = os.path.join(args.output_dir, rel)
                count = process_single_transcript(filepath, out_dir)
                total_files += 1
                total_convs += count

        print(f"\n{'='*60}")
        print(f"Total files processed: {total_files}")
        print(f"Total conversations extracted: {total_convs}")


if __name__ == "__main__":
    main()
