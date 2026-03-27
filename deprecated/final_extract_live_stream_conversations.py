#!/usr/bin/env python3
"""
Final script to extract individual audience conversations from live stream JSON.
Based on speaker pattern analysis.
"""

import json
import os
import re
from pathlib import Path

def load_json(file_path):
    """Load JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, file_path):
    """Save JSON file."""
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_timestamp(seconds):
    """Convert seconds to HHMMSS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}{minutes:02d}{secs:02d}"

def identify_conversations_by_guest_speaker(segments):
    """
    Identify conversations based on guest speaker patterns.
    SPEAKER_02 is the host (曲曲).
    SPEAKER_01, SPEAKER_03, SPEAKER_04, etc. are guests.
    """
    conversations = []
    current_guest = None
    current_start = None
    current_segments = []

    # Host speakers (not guests)
    host_speakers = {'SPEAKER_02', 'SPEAKER_00', 'UNKNOWN'}

    for i, seg in enumerate(segments):
        speaker = seg['speaker']

        # Check if this is a guest speaker
        if speaker not in host_speakers:
            # New guest or continuing with current guest
            if current_guest is None:
                # Start new conversation
                current_guest = speaker
                current_start = i
                current_segments = [seg]
            elif speaker == current_guest:
                # Continue current conversation
                current_segments.append(seg)
            else:
                # Different guest - check if we should end current conversation
                # Look ahead to see if current guest continues
                next_current_guest = False
                for j in range(i+1, min(i+10, len(segments))):
                    if segments[j]['speaker'] == current_guest:
                        next_current_guest = True
                        break

                if not next_current_guest:
                    # End current conversation
                    if current_segments:
                        conversations.append({
                            'guest_speaker': current_guest,
                            'start_idx': current_start,
                            'end_idx': i,
                            'segments': current_segments
                        })
                    # Start new conversation
                    current_guest = speaker
                    current_start = i
                    current_segments = [seg]
                else:
                    # Keep current conversation, add this segment
                    current_segments.append(seg)
        else:
            # Host speaker
            if current_guest is not None:
                # Add to current conversation
                current_segments.append(seg)

                # Check if conversation should end (long host-only section)
                # Look ahead for guest speaker
                next_guest_found = False
                for j in range(i+1, min(i+20, len(segments))):
                    if segments[j]['speaker'] == current_guest:
                        next_guest_found = True
                        break
                    elif segments[j]['speaker'] not in host_speakers:
                        # Different guest found
                        break

                if not next_guest_found:
                    # End conversation
                    if current_segments:
                        conversations.append({
                            'guest_speaker': current_guest,
                            'start_idx': current_start,
                            'end_idx': i+1,
                            'segments': current_segments
                        })
                    current_guest = None
                    current_start = None
                    current_segments = []

    # Add last conversation if exists
    if current_segments:
        conversations.append({
            'guest_speaker': current_guest,
            'start_idx': current_start,
            'end_idx': len(segments),
            'segments': current_segments
        })

    return conversations

def extract_guest_tag_from_intro(segments, guest_speaker):
    """
    Extract a tag for the guest based on their self-introduction.
    Look at the first few minutes of their dialogue.
    """
    # Get first 5 minutes of guest's speech
    guest_text = []
    start_time = None

    for seg in segments:
        if seg['speaker'] == guest_speaker:
            if start_time is None:
                start_time = seg['start']
            if seg['start'] - start_time > 300:  # 5 minutes
                break
            guest_text.append(seg['text'])

    full_text = ''.join(guest_text)

    # Extract age
    age = None
    age_match = re.search(r'(\d{2})岁', full_text)
    if age_match:
        age = age_match.group(1)

    # Extract profession/identity keywords
    profession_keywords = {
        '博士': '博士',
        '硕士': '硕士',
        '医生': '医生',
        '医学': '医学',
        '律师': '律师',
        '工程师': '工程师',
        '老师': '老师',
        '学生': '学生',
        '创业': '创业者',
        '投资': '投资',
        '金融': '金融',
        '咨询': '咨询',
        '精精': '精精',
        '大学': '大学生',
        '毕业': '毕业生',
    }

    profession = None
    for keyword, label in profession_keywords.items():
        if keyword in full_text:
            profession = label
            break

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(f"{age}岁")
    if profession:
        tag_parts.append(profession)

    if not tag_parts:
        # Use first meaningful words
        words = full_text.strip()[:15]
        tag_parts.append(words if words else guest_speaker)

    return ''.join(tag_parts)

def main():
    # Load merged segments
    with open('temp_merged_segments.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data['segments']

    print(f"Total merged segments: {len(segments)}")

    # Identify conversations
    conversations = identify_conversations_by_guest_speaker(segments)

    print(f"\nFound {len(conversations)} conversations")

    # Print conversation summary
    print("\n=== Conversation Summary ===")
    for i, conv in enumerate(conversations):
        start_time = conv['segments'][0]['start']
        end_time = conv['segments'][-1]['end']
        duration = (end_time - start_time) / 60

        # Extract tag
        tag = extract_guest_tag_from_intro(conv['segments'], conv['guest_speaker'])

        # Get all speakers in this conversation
        speakers = set(seg['speaker'] for seg in conv['segments'])

        print(f"\nConversation {i+1}:")
        print(f"  Guest: {conv['guest_speaker']}")
        print(f"  Tag: {tag}")
        print(f"  Time: {format_timestamp(start_time)}-{format_timestamp(end_time)} ({duration:.1f}min)")
        print(f"  Speakers: {sorted(speakers)}")
        print(f"  Segments: {len(conv['segments'])}")
        print(f"  First line: {conv['segments'][0]['text'][:80]}...")

        # Save conversation info
        conv['tag'] = tag
        conv['start_time'] = start_time
        conv['end_time'] = end_time

    # Save conversations for review
    output_file = "temp_conversations_identified.json"
    save_json({'conversations': [
        {
            'guest_speaker': c['guest_speaker'],
            'tag': c['tag'],
            'start_time': c['start_time'],
            'end_time': c['end_time'],
            'start_timestamp': format_timestamp(c['start_time']),
            'end_timestamp': format_timestamp(c['end_time']),
            'segment_count': len(c['segments'])
        }
        for c in conversations
    ]}, output_file)

    print(f"\nSaved conversation summary to {output_file}")

    return conversations

if __name__ == '__main__':
    main()
