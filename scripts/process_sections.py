#!/usr/bin/env python3
"""
Process transcript sections using traecli --yolo --print.
Generates formal output according to formal_output.schema.json.
"""
import json
import os
import subprocess
from pathlib import Path

def process_section(input_file, output_file, section_type, index):
    """Process a single section and generate formal output."""

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    meta = data['meta']
    segments = data['segments']

    if not segments:
        print(f"Warning: No segments in {input_file}")
        return

    # Determine speakers based on section type
    if section_type == "opening" or section_type == "comment":
        # Only host
        speaker_ids = ["host"]
        speaker_names = {"host": "曲曲"}
    else:  # call
        # Host + guest
        guest_speakers = set()
        for seg in segments:
            if seg['speaker'] != 'SPEAKER_01':
                guest_speakers.add(seg['speaker'])

        speaker_ids = ["host", "guest"]
        guest_name = list(guest_speakers)[0] if guest_speakers else "嘉宾"
        speaker_names = {"host": "曲曲", "guest": f"嘉宾{guest_name}"}

    # Merge segments into sentences
    # Group consecutive segments from same speaker
    sentences = []
    current_speaker_id = None
    current_start = None
    current_end = None
    current_texts = []

    def speaker_to_id(spk):
        if spk == "SPEAKER_01":
            return "host"
        elif section_type in ["opening", "comment"]:
            # For opening and comment, only host is allowed
            return "host" if spk == "SPEAKER_01" else None
        else:
            return "guest"

    def flush_sentence():
        nonlocal current_speaker_id, current_start, current_end, current_texts
        if current_texts and current_speaker_id:
            full_text = "".join(current_texts)
            if full_text.strip():
                sentences.append({
                    "speaker_id": current_speaker_id,
                    "speaker_name": speaker_names.get(current_speaker_id, current_speaker_id),
                    "start": current_start,
                    "end": current_end,
                    "text": full_text
                })
        current_speaker_id = None
        current_start = None
        current_end = None
        current_texts = []

    for seg in segments:
        spk_id = speaker_to_id(seg['speaker'])

        # Check if we should flush (different speaker or gap > 2s)
        if current_speaker_id and current_speaker_id != spk_id:
            flush_sentence()

        if current_speaker_id is None:
            current_speaker_id = spk_id
            current_start = seg['start']

        current_end = seg['end']
        current_texts.append(seg['text'])

    flush_sentence()

    # Build output
    start_ts = f"{int(segments[0]['start'] // 3600):02d}:{int((segments[0]['start'] % 3600) // 60):02d}:{segments[0]['start'] % 60:05.2f}"
    end_ts = f"{int(segments[-1]['end'] // 3600):02d}:{int((segments[-1]['end'] % 3600) // 60):02d}:{segments[-1]['end'] % 60:05.2f}"

    output = {
        "meta": {
            "source_file": os.path.basename(input_file),
            "index": index,
            "kind": section_type,
            "persona": "主播" if section_type in ["opening", "comment"] else "嘉宾",
            "title": meta.get('name', f"Section {index}"),
            "start": segments[0]['start'],
            "end": segments[-1]['end'],
            "start_ts": start_ts,
            "end_ts": end_ts,
            "raw_segment_count": len(segments),
            "speaker_ids": speaker_ids,
            "speaker_names": speaker_names,
            "sentence_count": len(sentences),
            "notes": ""
        },
        "sentences": sentences
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Processed: {input_file} -> {output_file} ({len(sentences)} sentences)")

def main():
    input_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/23_processed"
    output_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/23_processed/formal"
    os.makedirs(output_dir, exist_ok=True)

    # Define processing order and types
    files_to_process = [
        ("00_开场.json", "opening"),
        ("01_SPEAKER00_连麦.json", "call"),
        ("02_主播评论1.json", "comment"),
        ("03_SPEAKER02_连麦.json", "call"),
        ("04_主播评论2.json", "comment"),
        ("05_SPEAKER00_连麦.json", "call"),
        ("06_SPEAKER00_连麦.json", "call"),
        ("07_主播评论3.json", "comment"),
        ("08_SPEAKER00_连麦.json", "call"),
        ("09_SPEAKER02_连麦.json", "call"),
        ("10_SPEAKER00_连麦.json", "call"),
        ("11_主播评论4.json", "comment"),
        ("12_SPEAKER00_连麦.json", "call"),
        ("13_SPEAKER00_连麦.json", "call"),
        ("14_SPEAKER03_连麦.json", "call"),
        ("15_SPEAKER03_连麦.json", "call"),
    ]

    for i, (filename, section_type) in enumerate(files_to_process):
        input_file = os.path.join(input_dir, filename)
        if not os.path.exists(input_file):
            print(f"Warning: {input_file} not found, skipping")
            continue

        output_file = os.path.join(output_dir, f"{i:02d}_{filename}")
        process_section(input_file, output_file, section_type, i)

    print(f"\nAll files processed. Output saved to: {output_dir}")

if __name__ == "__main__":
    main()
