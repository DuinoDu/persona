#!/usr/bin/env python3
"""
Detailed conversation boundary analysis.
"""

import json

def load_json_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

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

def identify_conversations(merged_segments):
    """Identify conversation boundaries based on speaker patterns."""
    conversations = []
    current_guest = None
    current_start = None
    current_end = None

    for i, seg in enumerate(merged_segments):
        speaker = seg['speaker']

        # Guest speakers (not host SPEAKER_01 or SPEAKER_02)
        if speaker not in ['SPEAKER_01', 'SPEAKER_02', 'UNKNOWN']:
            if current_guest != speaker:
                # New guest started
                if current_guest is not None:
                    # Save previous conversation
                    conversations.append({
                        'guest_speaker': current_guest,
                        'start': current_start,
                        'end': current_end,
                        'start_idx': current_start_idx,
                        'end_idx': i - 1
                    })

                current_guest = speaker
                current_start = seg['start']
                current_start_idx = i

            current_end = seg['end']

    # Save last conversation
    if current_guest is not None:
        conversations.append({
            'guest_speaker': current_guest,
            'start': current_start,
            'end': current_end,
            'start_idx': current_start_idx,
            'end_idx': len(merged_segments) - 1
        })

    return conversations

def extract_guest_intro(merged_segments, start_idx, end_idx):
    """Extract guest introduction from first few segments."""
    intro_text = ""
    for i in range(start_idx, min(start_idx + 5, end_idx + 1)):
        seg = merged_segments[i]
        if seg['speaker'] not in ['SPEAKER_01', 'SPEAKER_02']:
            intro_text += seg['text'] + " "
            if len(intro_text) > 300:
                break

    return intro_text[:300]

def main():
    input_file = "06_downloads_json/曲曲2025（全）/20 - 曲曲現場直播 2025年3月21日 ｜ 曲曲麥肯錫.json"

    print(f"Loading {input_file}...")
    data = load_json_file(input_file)
    segments = data['segments']

    merged = merge_consecutive_segments(segments)
    print(f"Merged segments: {len(merged)}")

    conversations = identify_conversations(merged)
    print(f"\nFound {len(conversations)} conversations:\n")

    for i, conv in enumerate(conversations, 1):
        start_ts = format_timestamp(conv['start'])
        end_ts = format_timestamp(conv['end'])
        duration_min = (conv['end'] - conv['start']) / 60

        intro = extract_guest_intro(merged, conv['start_idx'], conv['end_idx'])

        print(f"Conversation {i}:")
        print(f"  Speaker: {conv['guest_speaker']}")
        print(f"  Time: {start_ts} - {end_ts} ({duration_min:.1f} minutes)")
        print(f"  Intro: {intro}")
        print()

if __name__ == "__main__":
    main()
