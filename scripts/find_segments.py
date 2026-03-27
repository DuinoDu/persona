#!/usr/bin/env python3
"""
精细分析直播字幕，精确识别：
- 开场白
- 连麦段落（主播+嘉宾双人对谈）
- 评论段落（主播单人总结/评论）
"""

import json
import sys
from collections import defaultdict

def format_time(seconds):
    """将秒数格式化为 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def detect_segment_type(segments, start_time, end_time, host_speaker='SPEAKER_01'):
    """
    检测一个时间段的类型
    返回: ('开场白'|'连麦'|'评论', 参与说话人列表)
    """
    # 获取该时间段内的所有片段
    relevant_segs = [
        seg for seg in segments
        if seg['start'] >= start_time and seg['end'] <= end_time
    ]

    if not relevant_segs:
        return '未知', []

    # 统计说话人
    speaker_counts = defaultdict(int)
    for seg in relevant_segs:
        speaker = seg.get('speaker', 'UNKNOWN')
        if speaker and speaker != 'UNKNOWN':
            speaker_counts[speaker] += 1

    speakers = list(speaker_counts.keys())
    has_host = host_speaker in speakers
    num_speakers = len([s for s in speakers if s != 'UNKNOWN'])

    # 判断类型
    if num_speakers >= 2 and has_host:
        return '连麦', speakers
    elif has_host and num_speakers == 1:
        return '评论', speakers
    else:
        return '评论', speakers

def find_segments(segments, host_speaker='SPEAKER_01'):
    """
    识别所有段落（开场白、连麦、评论）
    """
    # 首先找到所有可能的连麦段落（有双人对谈的区域）
    window_size = 50
    dialog_regions = []

    for i in range(0, len(segments) - window_size, 10):
        window = segments[i:i+window_size]
        speakers = set()
        for seg in window:
            speaker = seg.get('speaker', 'UNKNOWN')
            if speaker and speaker != 'UNKNOWN':
                speakers.add(speaker)

        # 如果有主播+至少一个其他人
        if host_speaker in speakers and len(speakers) >= 2:
            start_time = window[0]['start']
            end_time = window[-1]['end']
            dialog_regions.append({
                'start': start_time,
                'end': end_time,
                'speakers': list(speakers)
            })

    # 合并连续的对话区域
    merged_regions = []
    current = None

    for region in sorted(dialog_regions, key=lambda x: x['start']):
        if current is None:
            current = {
                'start': region['start'],
                'end': region['end'],
                'speakers': set(region['speakers'])
            }
        elif region['start'] - current['end'] < 180:  # 间隔小于3分钟，合并
            current['end'] = max(current['end'], region['end'])
            current['speakers'].update(region['speakers'])
        else:
            merged_regions.append({
                'start': current['start'],
                'end': current['end'],
                'speakers': list(current['speakers'])
            })
            current = {
                'start': region['start'],
                'end': region['end'],
                'speakers': set(region['speakers'])
            }

    if current:
        merged_regions.append({
            'start': current['start'],
            'end': current['end'],
            'speakers': list(current['speakers'])
        })

    # 构建最终的段落列表
    final_segments = []

    # 添加开场白（从第一个对话之前）
    if merged_regions and merged_regions[0]['start'] > 0:
        final_segments.append({
            'type': '开场白',
            'start': segments[0]['start'],
            'end': merged_regions[0]['start'] - 5,  # 稍微提前一点
            'speakers': [host_speaker]
        })

    # 添加对话段落和中间的评论段落
    prev_end = 0
    for i, region in enumerate(merged_regions):
        # 如果与前一个区域有间隔，添加评论段落
        if region['start'] - prev_end > 30:  # 间隔大于30秒
            final_segments.append({
                'type': '评论',
                'start': prev_end + 5 if prev_end > 0 else segments[0]['start'],
                'end': region['start'] - 5,
                'speakers': [host_speaker]
            })

        # 添加连麦段落
        final_segments.append({
            'type': '连麦',
            'start': region['start'],
            'end': region['end'],
            'speakers': region['speakers']
        })

        prev_end = region['end']

    # 添加结尾（如果最后一段不是评论）
    if final_segments and final_segments[-1]['type'] == '连麦':
        final_segments.append({
            'type': '评论',
            'start': final_segments[-1]['end'] + 5,
            'end': segments[-1]['end'],
            'speakers': [host_speaker]
        })

    return final_segments

def main(file_path):
    print(f"分析文件: {file_path}")
    print("=" * 80)

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('segments', [])

    if not segments:
        print("没有片段数据")
        return

    print(f"总片段数: {len(segments)}")

    # 获取时间范围
    first_time = segments[0]['start']
    last_time = segments[-1]['end']
    total_duration = last_time - first_time

    print(f"总时长: {format_time(total_duration)} ({total_duration/60:.2f} 分钟)")
    print()

    # 分析段落
    final_segments = find_segments(segments)

    # 过滤掉太短的段落（小于5秒）
    final_segments = [s for s in final_segments if s['end'] - s['start'] > 5]

    print(f"识别到 {len(final_segments)} 个段落:\n")
    print("=" * 80)

    call_count = 0
    comment_count = 0

    for i, seg in enumerate(final_segments):
        duration = seg['end'] - seg['start']
        seg_type = seg['type']

        if seg_type == '连麦':
            call_count += 1
            print(f"\n【连麦 {call_count}】段落 {i+1}")
        elif seg_type == '评论':
            comment_count += 1
            print(f"\n【评论 {comment_count}】段落 {i+1}")
        else:
            print(f"\n【{seg_type}】段落 {i+1}")

        print(f"  类型: {seg_type}")
        print(f"  时间: {format_time(seg['start'])} - {format_time(seg['end'])}")
        print(f"  持续: {format_time(duration)} ({duration/60:.2f} 分钟)")
        print(f"  说话人: {', '.join(seg['speakers'])}")

    print(f"\n\n{'=' * 80}")
    print(f"总结:")
    print(f"  - 总段落数: {len(final_segments)}")
    print(f"  - 连麦次数: {call_count}")
    print(f"  - 评论段落: {comment_count}")
    print(f"  - 开场白: 1" if any(s['type'] == '开场白' for s in final_segments) else "")

    # 保存结果
    output_file = file_path.replace('.json', '_segments.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_duration': total_duration,
            'segments': final_segments
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python find_segments.py <json_file>")
        sys.exit(1)

    main(sys.argv[1])
