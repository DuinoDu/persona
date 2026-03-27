#!/usr/bin/env python3
"""
Process transcript file 58 - 曲曲直播 2024年09月06日
Split into sections: opening, calls, comments
"""

import json
import os
from datetime import timedelta

def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS.ss format"""
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}"

def get_section_kind(index, total_calls):
    """Determine section kind based on index"""
    if index == 0:
        return "opening"
    elif index % 2 == 1 and (index + 1) // 2 <= total_calls:
        return "call"
    else:
        return "comment"

def detect_speaker_role(speaker_id, all_speakers_in_section):
    """
    Detect if speaker is host or guest
    SPEAKER_00 is always host (曲曲)
    Others are guests
    """
    if speaker_id == "SPEAKER_00":
        return "host", "曲曲"
    else:
        # Map other speakers to guest
        return "guest", f"嘉宾{speaker_id.replace('SPEAKER_', '')}"

def merge_segments_into_sentences(segments, section_speakers):
    """
    Merge short segments into proper sentences
    Keep speaker identification
    """
    sentences = []
    current_sentence = None

    for seg in segments:
        speaker_id = seg["speaker"]
        text = seg["text"].strip()

        if not text:
            continue

        # Determine speaker role
        role, name = detect_speaker_role(speaker_id, section_speakers)

        # Check if this is a continuation of current sentence
        # If same speaker and sentence doesn't end with punctuation
        if (current_sentence and
            current_sentence["speaker_id"] == role and
            not current_sentence["text"].endswith("。") and
            not current_sentence["text"].endswith("？") and
            not current_sentence["text"].endswith("！") and
            (current_sentence["end"] - seg["start"]) < 5):  # Less than 5 seconds gap
            # Merge with current sentence
            current_sentence["text"] += " " + text
            current_sentence["end"] = seg["end"]
        else:
            # Start new sentence
            if current_sentence:
                # Clean up previous sentence
                current_sentence["text"] = current_sentence["text"].strip()
                if current_sentence["text"]:
                    sentences.append(current_sentence)

            current_sentence = {
                "speaker_id": role,
                "speaker_name": name,
                "start": seg["start"],
                "end": seg["end"],
                "text": text
            }

    # Don't forget the last sentence
    if current_sentence:
        current_sentence["text"] = current_sentence["text"].strip()
        if current_sentence["text"]:
            sentences.append(current_sentence)

    return sentences

def process_transcript():
    """Main processing function"""

    # Load source file
    source_path = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/58 - 曲曲直播 2024年09月06日 曲曲大女人 美人解忧铺 #曲曲麦肯锡.json"

    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]

    # Define sections based on analysis
    # Format: (start_time, end_time, section_name, kind)
    sections = [
        (0, 1830, "00_开场", "opening"),
        (1830, 2170, "01_嘉宾1_连麦", "call"),
        (2170, 2260, "02_嘉宾1_评论", "comment"),
        (2260, 2570, "03_嘉宾2_连麦", "call"),
        (2570, 3880, "04_嘉宾2_评论", "comment"),
        (3880, 4450, "05_嘉宾3_连麦", "call"),
        (4450, 5070, "06_嘉宾3_评论", "comment"),
        (5070, 6770, "07_嘉宾4_评论", "comment"),
        (6770, 8080, "08_嘉宾5_连麦", "call"),
        (8080, 13220, "09_嘉宾5_评论", "comment"),
        (13220, 14586, "10_结尾", "comment"),
    ]

    output_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/58_processed"
    os.makedirs(output_dir, exist_ok=True)

    for idx, (start, end, name, kind) in enumerate(sections):
        # Filter segments for this section
        section_segments = [s for s in segments if s["start"] >= start and s["end"] <= end]

        if not section_segments:
            print(f"Skipping {name}: no segments")
            continue

        # Get unique speakers in this section
        section_speakers = set(s["speaker"] for s in section_segments)

        # Merge segments into sentences
        sentences = merge_segments_into_sentences(section_segments, section_speakers)

        # Determine speaker names
        speaker_names = {"host": "曲曲"}
        if kind == "call":
            # For calls, identify guest speaker
            guest_speaker = None
            for spk in section_speakers:
                if spk != "SPEAKER_00":
                    guest_speaker = spk
                    break
            if guest_speaker:
                speaker_names["guest"] = f"嘉宾{guest_speaker.replace('SPEAKER_', '')}"

        # Create output object
        output = {
            "meta": {
                "source_file": "58 - 曲曲直播 2024年09月06日 曲曲大女人 美人解忧铺 #曲曲麦肯锡.json",
                "index": idx,
                "kind": kind,
                "persona": "曲曲" if kind == "opening" else (speaker_names.get("guest", "嘉宾") if kind == "call" else ""),
                "title": name,
                "start": start,
                "end": end,
                "start_ts": format_timestamp(start),
                "end_ts": format_timestamp(end),
                "raw_segment_count": len(section_segments),
                "speaker_ids": ["host"] + (["guest"] if kind == "call" else []),
                "speaker_names": speaker_names,
                "sentence_count": len(sentences),
                "notes": ""
            },
            "sentences": sentences
        }

        # Save output
        output_path = os.path.join(output_dir, f"{name}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"Created {name}: {len(sentences)} sentences, {len(section_segments)} segments")

if __name__ == "__main__":
    process_transcript()
