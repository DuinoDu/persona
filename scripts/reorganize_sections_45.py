#!/usr/bin/env python3
"""
Reorganize transcript sections into a cleaner structure:
- 00_opening: Host introduction
- 01_call_1: First call session (guest + host interaction + follow-up comments)
- 02_call_2: Second call session
- etc.

Short comment sections (< 30s) will be merged with the preceding call.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List

@dataclass
class Segment:
    start: float
    end: float
    speaker: str
    text: str
    idx: int

@dataclass
class Section:
    name: str
    start_time: float
    end_time: float
    start_idx: int
    end_idx: int
    segments: List[Segment]

def load_segments(json_path: str) -> List[Segment]:
    """Load segments from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = []
    for idx, seg in enumerate(data['segments']):
        segments.append(Segment(
            start=seg['start'],
            end=seg['end'],
            speaker=seg['speaker'],
            text=seg['text'],
            idx=idx
        ))
    return segments

def identify_host(segments: List[Segment]) -> str:
    """Identify the host speaker (most frequent speaker)."""
    speaker_counts = {}
    for seg in segments:
        speaker_counts[seg.speaker] = speaker_counts.get(seg.speaker, 0) + 1
    
    return max(speaker_counts.items(), key=lambda x: x[1])[0]

def find_major_calls(segments: List[Segment], host: str, min_duration: float = 60.0) -> List[Section]:
    """Find major call sessions."""
    calls = []
    
    i = 0
    while i < len(segments):
        seg = segments[i]
        if seg.speaker != host:
            # Start of potential call
            call_start_idx = i
            guest_speaker = seg.speaker
            start_time = seg.start
            
            # Continue until host speaks again
            while i < len(segments) and segments[i].speaker != host:
                i += 1
            
            end_time = segments[i-1].end
            end_idx = i - 1
            duration = end_time - start_time
            
            if duration >= min_duration:
                call_segments = segments[call_start_idx:end_idx+1]
                calls.append(Section(
                    name=f"call_{len(calls)+1}_{guest_speaker}",
                    start_time=start_time,
                    end_time=end_time,
                    start_idx=call_start_idx,
                    end_idx=end_idx,
                    segments=call_segments
                ))
        else:
            i += 1
    
    return calls

def reorganize_sections(segments: List[Segment], host: str, min_call_duration: float = 60.0, min_comment_duration: float = 30.0) -> List[Section]:
    """
    Reorganize transcript into cleaner sections:
    - 00_opening: from start to first call
    - 01_call_1: first major call (includes guest-host interaction + follow-up comments until next call)
    - 02_call_2: second major call
    - etc.
    
    Short sections (< min_duration) are merged with adjacent sections.
    """
    sections = []
    
    # Find major calls
    calls = find_major_calls(segments, host, min_call_duration)
    print(f"Found {len(calls)} major calls")
    
    if not calls:
        # No calls found, treat everything as opening
        return [Section(
            name="00_opening",
            start_time=segments[0].start,
            end_time=segments[-1].end,
            start_idx=0,
            end_idx=len(segments) - 1,
            segments=segments
        )]
    
    # Build sections: opening + calls (with merged comments)
    current_idx = 0
    section_num = 0
    
    # Opening: from start to first call
    if calls[0].start_idx > 0:
        opening_segments = segments[0:calls[0].start_idx]
        sections.append(Section(
            name=f"{section_num:02d}_opening",
            start_time=segments[0].start,
            end_time=calls[0].start_time,
            start_idx=0,
            end_idx=calls[0].start_idx - 1,
            segments=opening_segments
        ))
        section_num += 1
    
    # Each call includes the call itself + following comments until next call
    for i, call in enumerate(calls):
        # Determine the end of this call section
        if i + 1 < len(calls):
            # End at the start of next call
            section_end_idx = calls[i + 1].start_idx - 1
        else:
            # Last call: end at the end of transcript
            section_end_idx = len(segments) - 1
        
        # Extract segments for this section (call + following comments)
        section_segments = segments[call.start_idx:section_end_idx + 1]
        
        # Get guest speaker from call
        guest_speaker = call.name.split('_')[-1]
        
        sections.append(Section(
            name=f"{section_num:02d}_call_{i+1}_{guest_speaker}",
            start_time=call.start_time,
            end_time=segments[section_end_idx].end,
            start_idx=call.start_idx,
            end_idx=section_end_idx,
            segments=section_segments
        ))
        section_num += 1
    
    return sections

def save_section(section: Section, output_dir: str):
    """Save a section to a JSON file."""
    output_path = os.path.join(output_dir, f"{section.name}.json")
    
    data = {
        "section_name": section.name,
        "start_time": section.start_time,
        "end_time": section.end_time,
        "duration": section.end_time - section.start_time,
        "num_segments": len(section.segments),
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "speaker": seg.speaker,
                "text": seg.text
            }
            for seg in section.segments
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  Saved {section.name}: {len(section.segments)} segments, {section.end_time - section.start_time:.1f}s")

def main():
    input_file = "data/03_transcripts/曲曲2024（全）/45 - 曲曲直播 2024年07月26日 久违的直播来啦，试直播中 #曲曲麦肯锡.json"
    output_dir = "data/03_transcripts/曲曲2024（全）/45_processed"
    
    print(f"Loading segments from {input_file}")
    segments = load_segments(input_file)
    print(f"Loaded {len(segments)} segments")
    
    # Identify host
    host = identify_host(segments)
    
    # Reorganize into cleaner sections
    print("\nReorganizing sections...")
    sections = reorganize_sections(segments, host, min_call_duration=60.0)
    
    print(f"\nReorganized into {len(sections)} sections:")
    for sec in sections:
        print(f"  {sec.name}: {sec.end_time - sec.start_time:.1f}s")
    
    # Save sections
    print(f"\nSaving sections to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    for section in sections:
        save_section(section, output_dir)
    
    print("\nDone!")

if __name__ == "__main__":
    main()
