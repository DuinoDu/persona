#!/usr/bin/env python3
"""
Process transcript sections: speaker identification and sentence segmentation.
"""
import json
import sys
import os
from datetime import timedelta

def format_ts(seconds):
    """Convert seconds to HH:MM:SS.mm format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"

def merge_segments_to_sentences(segments, speaker_id_map):
    """
    Merge consecutive segments from the same speaker into sentences.
    """
    sentences = []
    current_sentence = None

    for seg in segments:
        speaker_raw = seg['speaker']
        speaker_id = speaker_id_map.get(speaker_raw, speaker_raw)
        text = seg['text'].strip()

        if not text:
            continue

        # Check if this is a continuation from the same speaker
        if current_sentence and current_sentence['speaker_id'] == speaker_id:
            # Check if we should start a new sentence
            # New sentence indicators: text ends with punctuation and next text starts with certain words
            current_text = current_sentence['text']
            if (current_text.endswith(('。', '！', '？', '.', '!', '?', '」', '）', ')')) or
                text.startswith(('但是', '然后', '所以', '其实', '就是', '对', '嗯', '那个'))):
                # Save current sentence and start new one
                sentences.append(current_sentence)
                current_sentence = {
                    'speaker_id': speaker_id,
                    'speaker_name': 'host' if speaker_id == 'host' else 'guest',
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': text
                }
            else:
                # Continue current sentence
                current_sentence['text'] += text
                current_sentence['end'] = seg['end']
        else:
            # New speaker - save previous sentence if exists
            if current_sentence:
                sentences.append(current_sentence)
            # Start new sentence
            current_sentence = {
                'speaker_id': speaker_id,
                'speaker_name': 'host' if speaker_id == 'host' else 'guest',
                'start': seg['start'],
                'end': seg['end'],
                'text': text
            }

    # Don't forget the last sentence
    if current_sentence:
        sentences.append(current_sentence)

    return sentences

def process_section(input_file, section_info, output_file):
    """
    Process a single section of the transcript.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    all_segments = data['segments']

    # Filter segments for this section
    section_segments = [
        s for s in all_segments
        if s['start'] >= section_info['start'] and s['end'] <= section_info['end']
    ]

    if not section_segments:
        print(f"Warning: No segments found for section {section_info['index']}")
        return

    # Determine speaker mapping
    unique_speakers = set(s['speaker'] for s in section_segments)

    if section_info['kind'] == 'opening':
        # Opening: only host
        speaker_id_map = {sp: 'host' for sp in unique_speakers}
        speaker_names = {'host': '曲曲'}
    elif section_info['kind'] == 'call':
        # Call: host and guest
        guest_speaker = section_info.get('guest_speaker')
        speaker_id_map = {}
        for sp in unique_speakers:
            if sp == 'SPEAKER_01' or sp == guest_speaker:
                speaker_id_map[sp] = 'host' if sp == 'SPEAKER_01' else 'guest'
            else:
                # Other speakers (shouldn't happen in call)
                speaker_id_map[sp] = 'guest'
        speaker_names = {'host': '曲曲', 'guest': f'嘉宾{section_info["index"]}'}
    else:  # comment or closing
        # Only host
        speaker_id_map = {sp: 'host' for sp in unique_speakers}
        speaker_names = {'host': '曲曲'}

    # Merge segments into sentences
    sentences = merge_segments_to_sentences(section_segments, speaker_id_map)

    # Build output
    output = {
        'meta': {
            'source_file': input_file,
            'index': section_info['index'],
            'kind': section_info['kind'],
            'persona': section_info.get('persona') or '',
            'title': section_info['title'],
            'start': section_info['start'],
            'end': section_info['end'],
            'start_ts': format_ts(section_info['start']),
            'end_ts': format_ts(section_info['end']),
            'raw_segment_count': len(section_segments),
            'speaker_ids': sorted(list(set(s['speaker_id'] for s in sentences)), key=lambda x: {'host': 0, 'guest': 1}.get(x, 2)) if sentences else [],
            'speaker_names': speaker_names,
            'sentence_count': len(sentences),
            'notes': ''
        },
        'sentences': sentences
    }

    # Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Processed section {section_info['index']}: {len(sentences)} sentences, {len(section_segments)} segments -> {output_file}")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python process_section_47.py <input_file> <section_json> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    section_info = json.loads(sys.argv[2])
    output_file = sys.argv[3]

    process_section(input_file, section_info, output_file)
