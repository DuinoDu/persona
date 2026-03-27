#!/usr/bin/env python3
"""
精确分析直播字幕，识别：
1. 开场白（主播单人说话，直到第一个嘉宾上麦）
2. 连麦段落（主播+嘉宾双人对谈）
3. 评论段落（主播单人总结/评论）
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

def find_first_guest_entry(segments, host_speaker='SPEAKER_01'):
    """
    找到第一个嘉宾上麦的时间点
    规则：从主播开始说话后，找到第一个其他说话人的出现
    """
    host_started = False

    for i, seg in enumerate(segments):
        speaker = seg.get('speaker', 'UNKNOWN')

        if speaker == host_speaker:
            host_started = True

        if host_started and speaker != host_speaker and speaker != 'UNKNOWN':
            # 找到第一个嘉宾上麦
            return seg['start']

    return None

def analyze_segments(segments, host_speaker='SPEAKER_01'):
    """
    精细分析段落
    """
    # 1. 找到开场白结束时间（第一个嘉宾上麦）
    first_guest_time = find_first_guest_entry(segments, host_speaker)

    # 2. 使用滑动窗口找到所有双人对谈区域
    window_size = 40
    dialog_regions = []

    for i in range(0, len(segments) - window_size, 15):
        window = segments[i:i+window_size]
        speakers = set()

        for seg in window:
            speaker = seg.get('speaker', 'UNKNOWN')
            if speaker and speaker != 'UNKNOWN':
                speakers.add(speaker)

        # 主播+至少一个其他人 = 连麦
        if host_speaker in speakers and len(speakers) >= 2:
            start_time = window[0]['start']
            end_time = window[-1]['end']
            dialog_regions.append({
                'start': start_time,
                'end': end_time,
                'speakers': list(speakers)
            })

    # 3. 合并连续的对话区域
    merged_regions = []
    current = None

    for region in sorted(dialog_regions, key=lambda x: x['start']):
        if current is None:
            current = {
                'start': region['start'],
                'end': region['end'],
                'speakers': set(region['speakers'])
            }
        elif region['start'] - current['end'] < 150:  # 间隔小于2.5分钟，合并
            current['end'] = max(current['end'], region['end'])
            current['speakers'].update(region['speakers'])
        else:
            if len(current['speakers']) >= 2 and host_speaker in current['speakers']:
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

    if current and len(current['speakers']) >= 2 and host_speaker in current['speakers']:
        merged_regions.append({
            'start': current['start'],
            'end': current['end'],
            'speakers': list(current['speakers'])
        })

    # 4. 构建最终段落列表
    final_segments = []

    # 添加开场白（从开头到第一个嘉宾上麦）
    if first_guest_time:
        final_segments.append({
            'type': '开场白',
            'start': segments[0]['start'],
            'end': first_guest_time - 2,  # 稍微提前一点
            'speakers': [host_speaker]
        })

    # 添加连麦和评论段落
    prev_end = first_guest_time if first_guest_time else 0

    for i, region in enumerate(merged_regions):
        # 如果与前一个连麦有间隔，添加评论段落
        if region['start'] - prev_end > 20:  # 间隔大于20秒
            final_segments.append({
                'type': '评论',
                'start': prev_end + 2 if prev_end > 0 else segments[0]['start'],
                'end': region['start'] - 2,
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

    # 添加结尾评论
    if final_segments and final_segments[-1]['type'] == '连麦':
        final_segments.append({
            'type': '评论',
            'start': final_segments[-1]['end'] + 2,
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
    final_segments = analyze_segments(segments)

    # 过滤掉太短的段落
    final_segments = [s for s in final_segments if s['end'] - s['start'] > 5]

    # 统计
    call_count = sum(1 for s in final_segments if s['type'] == '连麦')
    comment_count = sum(1 for s in final_segments if s['type'] == '评论')
    intro_count = sum(1 for s in final_segments if s['type'] == '开场白')

    print(f"识别到 {len(final_segments)} 个段落:\n")
    print("=" * 80)

    call_idx = 0
    comment_idx = 0

    for i, seg in enumerate(final_segments):
        duration = seg['end'] - seg['start']
        seg_type = seg['type']

        if seg_type == '连麦':
            call_idx += 1
            print(f"\n【连麦 {call_idx}】段落 {i+1}")
        elif seg_type == '评论':
            comment_idx += 1
            print(f"\n【评论 {comment_idx}】段落 {i+1}")
        else:
            print(f"\n【{seg_type}】段落 {i+1}")

        print(f"  类型: {seg_type}")
        print(f"  时间: {format_time(seg['start'])} - {format_time(seg['end'])}")
        print(f"  持续: {format_time(duration)} ({duration/60:.2f} 分钟)")
        print(f"  说话人: {', '.join(seg['speakers'])}")

    print(f"\n\n{'=' * 80}")
    print(f"总结:")
    print(f"  - 总段落数: {len(final_segments)}")
    print(f"  - 开场白: {intro_count}")
    print(f"  - 连麦次数: {call_count}")
    print(f"  - 评论段落: {comment_count}")

    # 保存结果
    output_file = file_path.replace('.json', '_final_segments.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_duration': total_duration,
            'total_segments': len(final_segments),
            'intro_count': intro_count,
            'call_count': call_count,
            'comment_count': comment_count,
            'segments': final_segments
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

    return final_segments

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python final_segment_analysis.py <json_file>")
        sys.exit(1)

    main(sys.argv[1])
