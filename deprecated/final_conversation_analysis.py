#!/usr/bin/env python3
"""
Final polished version with improved age extraction.
"""

import json
import re
from collections import defaultdict

def load_json(file_path):
    """Load the JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def identify_host(segments):
    """Identify the host speaker."""
    speaker_texts = {}

    for seg in segments:
        speaker = seg['speaker']
        text = seg['text']

        if speaker not in speaker_texts:
            speaker_texts[speaker] = []
        speaker_texts[speaker].append(text)

    greeting_keywords = ['哈喽', '你好', '来下一个', '下一位', '拜拜']

    speaker_scores = {}
    for speaker, texts in speaker_texts.items():
        combined_text = ''.join(texts)
        score = sum(combined_text.count(kw) for kw in greeting_keywords)
        speaker_scores[speaker] = score

    host = max(speaker_scores, key=speaker_scores.get)
    return host

def build_speaker_profiles(segments, host):
    """Build profiles for each speaker."""
    speaker_profiles = defaultdict(list)

    for seg in segments:
        speaker = seg['speaker']
        if speaker != host and speaker != 'UNKNOWN':
            speaker_profiles[speaker].append(seg['text'])

    return speaker_profiles

def extract_tag_from_text(text):
    """Extract tag from text with improved patterns."""

    # Self-referential age patterns (more specific)
    age_patterns = [
        r'我今年(\d{2})岁',
        r'我(\d{2})岁',
        r'我是(\d{2})岁',
    ]

    education_patterns = [
        r'(硕士|博士|本科|大学生|研究生|大专|高中)',
        r'(读硕|读博|读研)',
    ]

    occupation_patterns = [
        r'我是.*?(程序员|工程师|医生|老师|学生|律师|会计|设计师|产品经理|销售|HR|运营|管理层)',
        r'(程序员|工程师|医生|老师|学生|律师|会计|设计师|产品经理|销售|HR|运营|管理层)',
        r'做.*?(开发|设计|销售|运营|管理)',
        r'(国企|外企|私企|创业)',
    ]

    # Try to find age (self-referential only)
    age = None
    for pattern in age_patterns:
        match = re.search(pattern, text)
        if match:
            age = match.group(1)
            # Validate age is reasonable (20-60)
            if 20 <= int(age) <= 60:
                break
            else:
                age = None

    # If no self-referential age found, try general pattern but be more careful
    if not age:
        general_age_pattern = r'(\d{2})岁'
        matches = re.findall(general_age_pattern, text)
        # Take the first reasonable age
        for match in matches:
            if 20 <= int(match) <= 60:
                age = match
                break

    # Try to find education
    education = None
    for pattern in education_patterns:
        match = re.search(pattern, text)
        if match:
            education = match.group(1)
            if education in ['读硕']:
                education = '硕士'
            elif education in ['读博']:
                education = '博士'
            break

    # Try to find occupation
    occupation = None
    for pattern in occupation_patterns:
        match = re.search(pattern, text)
        if match:
            occupation = match.group(1)
            break

    # Build tag
    if age and education:
        return f"{age}岁{education}"
    elif age and occupation:
        return f"{age}岁{occupation}"
    elif age:
        return f"{age}岁"
    elif education:
        return education
    elif occupation:
        return occupation
    else:
        # Try gender
        gender_patterns = [r'(男生|女生)', r'(单身|已婚|离异)']
        for pattern in gender_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return "未知"

def find_conversations(segments, host):
    """Find conversations."""

    conversations = []
    current_guest = None
    conv_start_idx = None
    conv_start_time = None
    last_guest_time = None

    for i, seg in enumerate(segments):
        speaker = seg['speaker']

        if speaker == host or speaker == 'UNKNOWN':
            if current_guest and last_guest_time:
                if seg['start'] - last_guest_time > 120:
                    conversations.append({
                        'guest': current_guest,
                        'start_idx': conv_start_idx,
                        'end_idx': i - 1,
                        'start_time': conv_start_time,
                        'end_time': segments[i-1]['end']
                    })
                    current_guest = None
                    conv_start_idx = None
                    conv_start_time = None
                    last_guest_time = None
            continue

        if current_guest is None:
            current_guest = speaker
            conv_start_idx = i
            conv_start_time = seg['start']
            last_guest_time = seg['end']
        elif speaker == current_guest:
            last_guest_time = seg['end']
        else:
            if seg['start'] - last_guest_time < 60:
                pass
            else:
                conversations.append({
                    'guest': current_guest,
                    'start_idx': conv_start_idx,
                    'end_idx': i - 1,
                    'start_time': conv_start_time,
                    'end_time': segments[i-1]['end']
                })
                current_guest = speaker
                conv_start_idx = i
                conv_start_time = seg['start']
                last_guest_time = seg['end']

    if current_guest:
        conversations.append({
            'guest': current_guest,
            'start_idx': conv_start_idx,
            'end_idx': len(segments) - 1,
            'start_time': conv_start_time,
            'end_time': segments[-1]['end']
        })

    return conversations

def find_greeting_before(segments, host, idx, window=30):
    """Find greeting from host."""
    greeting_patterns = [r'哈喽', r'你好', r'喂']

    for i in range(max(0, idx - window), idx):
        if segments[i]['speaker'] == host:
            text = segments[i]['text']
            for pattern in greeting_patterns:
                if re.search(pattern, text):
                    return segments[i]['start']
    return None

def find_goodbye_after(segments, host, idx, window=30):
    """Find goodbye from host."""
    goodbye_patterns = [r'拜拜', r'好.*?下一个', r'来.*?下一个', r'下一位']

    for i in range(idx, min(len(segments), idx + window)):
        if segments[i]['speaker'] == host:
            text = segments[i]['text']
            for pattern in goodbye_patterns:
                if re.search(pattern, text):
                    return segments[i]['end']
    return None

def refine_boundaries(segments, host, conversations, speaker_profiles):
    """Refine conversation boundaries."""

    refined = []

    for conv in conversations:
        start_idx = conv['start_idx']
        end_idx = conv['end_idx']
        start_time = conv['start_time']
        end_time = conv['end_time']
        guest = conv['guest']

        # Look for greeting before
        greeting_time = find_greeting_before(segments, host, start_idx)
        if greeting_time and start_time - greeting_time < 60:
            start_time = greeting_time

        # Look for goodbye after
        goodbye_time = find_goodbye_after(segments, host, end_idx)
        if goodbye_time and goodbye_time - end_time < 60:
            end_time = goodbye_time

        # Extract tag
        full_text = ''.join(speaker_profiles[guest])
        tag = extract_tag_from_text(full_text)

        if not tag:
            tag = "未知"

        refined.append({
            'guest': guest,
            'start_time': start_time,
            'end_time': end_time,
            'tag': tag,
            'duration': end_time - start_time,
            'start_idx': start_idx,
            'end_idx': end_idx
        })

    return refined

def merge_short_conversations(conversations, min_duration=180):
    """Merge very short conversations."""

    if not conversations:
        return []

    merged = []
    i = 0

    while i < len(conversations):
        conv = conversations[i]

        if conv['duration'] < min_duration and i + 1 < len(conversations):
            next_conv = conversations[i + 1]

            if next_conv['start_time'] - conv['end_time'] < 120:
                merged_conv = {
                    'guest': f"{conv['guest']}/{next_conv['guest']}",
                    'start_time': conv['start_time'],
                    'end_time': next_conv['end_time'],
                    'tag': next_conv['tag'],
                    'duration': next_conv['end_time'] - conv['start_time']
                }
                merged.append(merged_conv)
                i += 2
                continue

        merged.append(conv)
        i += 1

    return merged

def filter_intro_outro(conversations, min_duration=300):
    """Filter out intro/outro segments."""

    filtered = []

    for i, conv in enumerate(conversations):
        if i < 2 and conv['duration'] < min_duration:
            continue

        filtered.append(conv)

    return filtered

def main():
    file_path = "/home/duino/ws/ququ/process_youtube/06_downloads_json/曲曲2025（全）/04 - 曲曲現場直播 2025年1月10日 ｜ 曲曲麥肯錫.json"

    print("Loading JSON file...")
    data = load_json(file_path)
    segments = data['segments']

    print(f"Total segments: {len(segments)}")
    print(f"Duration: {segments[0]['start']:.2f}s - {segments[-1]['end']:.2f}s")
    print(f"Total duration: {(segments[-1]['end'] - segments[0]['start']) / 60:.2f} minutes")

    # Identify host
    host = identify_host(segments)
    print(f"\nIdentified host: {host}")

    # Build speaker profiles
    speaker_profiles = build_speaker_profiles(segments, host)
    print(f"Found {len(speaker_profiles)} guest speakers")

    # Find conversations
    conversations = find_conversations(segments, host)
    print(f"Found {len(conversations)} raw conversations")

    # Refine boundaries
    refined = refine_boundaries(segments, host, conversations, speaker_profiles)

    # Merge short conversations
    merged = merge_short_conversations(refined, min_duration=180)

    # Filter intro/outro
    final = filter_intro_outro(merged, min_duration=300)

    print(f"\n{'='*70}")
    print(f"FINAL RESULT: {len(final)} conversations identified")
    print(f"{'='*70}\n")

    total_duration = 0
    for i, conv in enumerate(final):
        duration_min = conv['duration'] / 60
        total_duration += conv['duration']
        print(f"{i+1:2d}. {conv['start_time']:7.2f}s - {conv['end_time']:7.2f}s "
              f"({duration_min:5.2f} min) | {conv['guest']:12s} | {conv['tag']}")

    stream_duration = segments[-1]['end'] - segments[0]['start']
    print(f"\nTotal conversation time: {total_duration/60:.2f} minutes")
    print(f"Stream duration: {stream_duration/60:.2f} minutes")
    print(f"Coverage: {total_duration/stream_duration*100:.1f}%")

    print("\n" + "="*70)
    print("Python list of tuples:")
    print("="*70)
    print("conversations = [")
    for conv in final:
        print(f"    ({conv['start_time']:.2f}, {conv['end_time']:.2f}, '{conv['tag']}'),")
    print("]")

    return final

if __name__ == "__main__":
    main()
