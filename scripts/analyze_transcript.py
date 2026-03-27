#!/usr/bin/env python3
"""分析直播字幕文件，识别连麦段落的工具"""

import json
import sys
from collections import defaultdict

def analyze_transcript(file_path):
    """分析字幕文件，提取说话人和时间信息"""

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('segments', [])

    print(f"总片段数: {len(segments)}")

    # 统计说话人
    speaker_stats = defaultdict(lambda: {'count': 0, 'total_duration': 0, 'first_appear': None, 'last_appear': None})

    for seg in segments:
        speaker = seg.get('speaker', 'UNKNOWN')
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        duration = end - start

        speaker_stats[speaker]['count'] += 1
        speaker_stats[speaker]['total_duration'] += duration

        if speaker_stats[speaker]['first_appear'] is None:
            speaker_stats[speaker]['first_appear'] = start
        speaker_stats[speaker]['last_appear'] = end

    print("\n=== 说话人统计 ===")
    for speaker, stats in sorted(speaker_stats.items()):
        print(f"\n{speaker}:")
        print(f"  片段数: {stats['count']}")
        print(f"  总时长: {stats['total_duration']:.2f}秒 ({stats['total_duration']/60:.2f}分钟)")
        print(f"  首次出现: {stats['first_appear']:.2f}秒 ({stats['first_appear']/60:.2f}分钟)")
        print(f"  最后出现: {stats['last_appear']:.2f}秒 ({stats['last_appear']/60:.2f}分钟)")

    # 分析对话模式 - 寻找连麦段落
    print("\n=== 对话模式分析 ===")

    # 滑动窗口分析说话人变化
    window_size = 20
    speaker_changes = []

    for i in range(0, len(segments) - window_size, window_size // 2):
        window = segments[i:i+window_size]
        speakers_in_window = set(seg.get('speaker', 'UNKNOWN') for seg in window)

        if len(speakers_in_window) > 1:
            speaker_changes.append({
                'start_idx': i,
                'start_time': window[0]['start'],
                'speakers': list(speakers_in_window)
            })

    # 合并连续的对话段落
    merged_segments = []
    current_segment = None

    for change in speaker_changes:
        if current_segment is None:
            current_segment = {
                'start': change['start_time'],
                'speakers': set(change['speakers'])
            }
        elif change['start_time'] - current_segment.get('end', change['start_time']) < 60:  # 60秒内合并
            current_segment['speakers'].update(change['speakers'])
        else:
            current_segment['end'] = change['start_time']
            if len(current_segment['speakers']) > 1:  # 只保留有对话的段落
                merged_segments.append(current_segment)
            current_segment = {
                'start': change['start_time'],
                'speakers': set(change['speakers'])
            }

    if current_segment:
        current_segment['end'] = segments[-1]['end'] if segments else 0
        if len(current_segment['speakers']) > 1:
            merged_segments.append(current_segment)

    print(f"\n发现 {len(merged_segments)} 个可能的对话/连麦段落:\n")

    for i, seg in enumerate(merged_segments[:20]):  # 只显示前20个
        duration = seg.get('end', 0) - seg.get('start', 0)
        print(f"段落 {i+1}:")
        print(f"  时间: {seg['start']:.2f}s - {seg.get('end', 0):.2f}s (持续 {duration:.2f}s / {duration/60:.2f}min)")
        print(f"  说话人: {', '.join(seg['speakers'])}")
        print()

    # 保存详细结果到文件
    output_file = file_path.replace('.json', '_analysis.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=== 字幕分析结果 ===\n\n")
        f.write(f"总片段数: {len(segments)}\n\n")

        f.write("=== 说话人统计 ===\n")
        for speaker, stats in sorted(speaker_stats.items()):
            f.write(f"\n{speaker}:\n")
            f.write(f"  片段数: {stats['count']}\n")
            f.write(f"  总时长: {stats['total_duration']:.2f}秒\n")
            f.write(f"  首次出现: {stats['first_appear']:.2f}秒\n")
            f.write(f"  最后出现: {stats['last_appear']:.2f}秒\n")

        f.write(f"\n=== 对话段落 ({len(merged_segments)}个) ===\n")
        for i, seg in enumerate(merged_segments):
            duration = seg.get('end', 0) - seg.get('start', 0)
            f.write(f"\n段落 {i+1}:\n")
            f.write(f"  时间: {seg['start']:.2f}s - {seg.get('end', 0):.2f}s\n")
            f.write(f"  持续: {duration:.2f}s ({duration/60:.2f}min)\n")
            f.write(f"  说话人: {', '.join(seg['speakers'])}\n")

    print(f"\n详细分析结果已保存到: {output_file}")

    return merged_segments, speaker_stats

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_transcript.py <json_file>")
        sys.exit(1)

    file_path = sys.argv[1]
    analyze_transcript(file_path)
