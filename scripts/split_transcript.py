#!/usr/bin/env python3
"""
Process transcript file and split into sections based on call/comment structure.
"""
import json
import os
import sys

def main():
    input_file = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/23 - 未删减修复版 2024年05月09日 做的挺费劲 记得点赞评论 谢谢🙏 全网唯一哦 #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺.json"

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data['segments']

    # Define structure based on analysis
    # Format: (start_time, end_time, section_type, description)
    # section_type: "opening", "call", "comment"
    structure = [
        (0, 300, "opening", "00_开场"),  # 0-5min
        (300, 1020, "call", "01_SPEAKER00_连麦"),  # 5-17min
        (1020, 1260, "comment", "02_主播评论1"),  # 17-21min
        (1260, 2040, "call", "03_SPEAKER02_连麦"),  # 21-34min
        (2040, 2760, "comment", "04_主播评论2"),  # 34-46min
        (2760, 3600, "call", "05_SPEAKER00_连麦"),  # 46-60min
        (3600, 4800, "call", "06_SPEAKER00_连麦"),  # 60-80min
        (4800, 5880, "comment", "07_主播评论3"),  # 80-98min
        (5880, 7200, "call", "08_SPEAKER00_连麦"),  # 98-120min
        (7200, 8400, "call", "09_SPEAKER02_连麦"),  # 120-140min
        (8400, 9600, "call", "10_SPEAKER00_连麦"),  # 140-160min
        (9600, 10800, "comment", "11_主播评论4"),  # 160-180min
        (10800, 12000, "call", "12_SPEAKER00_连麦"),  # 180-200min
        (12000, 13200, "call", "13_SPEAKER00_连麦"),  # 200-220min
        (13200, 14400, "call", "14_SPEAKER03_连麦"),  # 220-240min
        (14400, 14973, "call", "15_SPEAKER03_连麦"),  # 240-249.6min
    ]

    output_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/23_processed"
    os.makedirs(output_dir, exist_ok=True)

    # Split segments into sections
    for i, (start, end, section_type, name) in enumerate(structure):
        section_segments = []
        for seg in segments:
            if seg['start'] >= start and seg['end'] <= end:
                section_segments.append(seg)
            elif seg['start'] < end and seg['end'] > start:
                # Partial overlap
                overlap_start = max(seg['start'], start)
                overlap_end = min(seg['end'], end)
                if overlap_end > overlap_start:
                    section_segments.append({
                        'start': overlap_start,
                        'end': overlap_end,
                        'speaker': seg['speaker'],
                        'text': seg['text']
                    })

        if section_segments:
            output_file = os.path.join(output_dir, f"{name}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'meta': {
                        'section_type': section_type,
                        'start': start,
                        'end': end,
                        'name': name
                    },
                    'segments': section_segments
                }, f, ensure_ascii=False, indent=2)
            print(f"Created: {output_file} ({len(section_segments)} segments)")

    print(f"\nAll sections saved to: {output_dir}")

if __name__ == "__main__":
    main()
