#!/usr/bin/env python3
"""
Analyze and segment live stream transcript into sections:
- Opening (主播开场)
- Call sessions (连麦 - guest speaking with host)
- Comments (评论 - host speaking alone after call)
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

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
    speaker_pattern: str  # 'host', 'guest', 'mixed'

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
    
    host = max(speaker_counts.items(), key=lambda x: x[1])[0]
    print(f"Identified host: {host} (appears {speaker_counts[host]} times)")
    return host

def find_major_calls(segments: List[Segment], host: str, min_duration: float = 30.0) -> List[Section]:
    """Find major call sessions (guest speaking for extended periods)."""
    calls = []
    
    # Group consecutive segments by guest speakers
    i = 0
    while i < len(segments):
        seg = segments[i]
        if seg.speaker != host:
            # Start of potential call session
            call_start = i
            guest_speaker = seg.speaker
            start_time = seg.start
            
            # Continue until host speaks again or we hit another guest
            while i < len(segments) and segments[i].speaker != host:
                i += 1
            
            end_time = segments[i-1].end
            duration = end_time - start_time
            
            if duration >= min_duration:
                calls.append(Section(
                    name=f"call_{guest_speaker}_{len(calls)}",
                    start_time=start_time,
                    end_time=end_time,
                    start_idx=call_start,
                    end_idx=i-1,
                    speaker_pattern='guest'
                ))
        else:
            i += 1
    
    return calls

def find_sections(segments: List[Segment], host: str) -> List[Section]:
    """Divide transcript into major sections."""
    sections = []
    
    # Find major calls first
    calls = find_major_calls(segments, host, min_duration=60.0)
    print(f"Found {len(calls)} major call sessions")
    
    # Build section list
    current_pos = 0
    section_num = 0
    
    # Opening section (from start to first call)
    if calls and calls[0].start_idx > 0:
        opening = Section(
            name=f"{section_num:02d}_opening",
            start_time=segments[0].start,
            end_time=calls[0].start_time,
            start_idx=0,
            end_idx=calls[0].start_idx - 1,
            speaker_pattern='host'
        )
        sections.append(opening)
        section_num += 1
        current_pos = calls[0].start_idx
    
    # Process each call and following comment
    for i, call in enumerate(calls):
        # Add the call section
        call_section = Section(
            name=f"{section_num:02d}_call_{i+1}",
            start_time=call.start_time,
            end_time=call.end_time,
            start_idx=call.start_idx,
            end_idx=call.end_idx,
            speaker_pattern='mixed'
        )
        sections.append(call_section)
        section_num += 1
        
        # Add comment section (host speaking alone until next call or end)
        comment_start_idx = call.end_idx + 1
        if i + 1 < len(calls):
            comment_end_idx = calls[i + 1].start_idx - 1
        else:
            comment_end_idx = len(segments) - 1
        
        if comment_start_idx <= comment_end_idx:
            comment = Section(
                name=f"{section_num:02d}_comment_{i+1}",
                start_time=segments[comment_start_idx].start,
                end_time=segments[comment_end_idx].end,
                start_idx=comment_start_idx,
                end_idx=comment_end_idx,
                speaker_pattern='host'
            )
            sections.append(comment)
            section_num += 1
    
    # If no calls found, treat everything as opening
    if not sections:
        opening = Section(
            name="00_opening",
            start_time=segments[0].start,
            end_time=segments[-1].end,
            start_idx=0,
            end_idx=len(segments) - 1,
            speaker_pattern='host'
        )
        sections.append(opening)
    
    return sections

def save_section(segments: List[Segment], section: Section, output_dir: str):
    """Save a section to a JSON file."""
    output_path = os.path.join(output_dir, f"{section.name}.json")
    
    section_segments = segments[section.start_idx:section.end_idx + 1]
    
    data = {
        "section_name": section.name,
        "start_time": section.start_time,
        "end_time": section.end_time,
        "speaker_pattern": section.speaker_pattern,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "speaker": seg.speaker,
                "text": seg.text
            }
            for seg in section_segments
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  Saved {section.name}: {len(section_segments)} segments, duration {section.end_time - section.start_time:.1f}s")

def main():
    # Input file
    input_file = "data/03_transcripts/曲曲2024（全）/45 - 曲曲直播 2024年07月26日 久违的直播来啦，试直播中 #曲曲麦肯锡.json"
    output_dir = "data/03_transcripts/曲曲2024（全）/45_processed"
    
    print(f"Loading segments from {input_file}")
    segments = load_segments(input_file)
    print(f"Loaded {len(segments)} segments")
    
    # Identify host
    host = identify_host(segments)
    
    # Find sections
    print("\nFinding sections...")
    sections = find_sections(segments, host)
    
    print(f"\nFound {len(sections)} sections:")
    for sec in sections:
        print(f"  {sec.name}: {sec.start_time:.1f}s - {sec.end_time:.1f}s ({sec.end_time - sec.start_time:.1f}s)")
    
    # Save sections
    print(f"\nSaving sections to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    for section in sections:
        save_section(segments, section, output_dir)
    
    print("\nDone!")

if __name__ == "__main__":
    main()
