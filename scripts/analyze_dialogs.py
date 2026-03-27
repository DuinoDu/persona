#!/usr/bin/env python3
"""
更精细地分析直播字幕，识别连麦段落
策略：
1. 开场白：从 SPEAKER_01 首次出现开始，到第一个嘉宾开始连麦
2. 连麦段落：有两位说话人交替对话的段落（嘉宾 + 主播）
3. 评论段落：主播单独说话，可能是对前一个连麦的评论
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

def analyze_segments(segments):
    """分析段落，识别连麦模式"""

    # 滑动窗口分析 - 识别双人对谈段落
    window_size = 30  # 30个片段的窗口
    dialog_segments = []

    for i in range(len(segments)):
        # 获取当前窗口
        end_idx = min(i + window_size, len(segments))
        window = segments[i:end_idx]

        # 统计窗口内的说话人
        speakers = set()
        for seg in window:
            speaker = seg.get('speaker', 'UNKNOWN')
            if speaker and speaker != 'UNKNOWN':
                speakers.add(speaker)

        # 如果窗口内有两个以上的说话人，标记为对话段落
        if len(speakers) >= 2:
            start_time = window[0]['start']
            end_time = window[-1]['end']
            dialog_segments.append({
                'start': start_time,
                'end': end_time,
                'speakers': list(speakers),
                'start_idx': i
            })

    # 合并连续的对话段落
    merged_dialogs = []
    current = None

    for seg in sorted(dialog_segments, key=lambda x: x['start']):
        if current is None:
            current = {
                'start': seg['start'],
                'end': seg['end'],
                'speakers': set(seg['speakers'])
            }
        elif seg['start'] - current['end'] < 120:  # 间隔小于2分钟，合并
            current['end'] = max(current['end'], seg['end'])
            current['speakers'].update(seg['speakers'])
        else:
            # 检查是否是真正的对话（至少2个说话人）
            if len(current['speakers']) >= 2:
                merged_dialogs.append({
                    'start': current['start'],
                    'end': current['end'],
                    'speakers': list(current['speakers'])
                })
            current = {
                'start': seg['start'],
                'end': seg['end'],
                'speakers': set(seg['speakers'])
            }

    # 添加最后一个
    if current and len(current['speakers']) >= 2:
        merged_dialogs.append({
            'start': current['start'],
            'end': current['end'],
            'speakers': list(current['speakers'])
        })

    return merged_dialogs

def main(file_path):
    print(f"分析文件: {file_path}")
    print("=" * 60)

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('segments', [])
    print(f"总片段数: {len(segments)}")

    if not segments:
        print("没有片段数据")
        return

    # 获取时间范围
    first_time = segments[0]['start']
    last_time = segments[-1]['end']
    total_duration = last_time - first_time

    print(f"总时长: {format_time(total_duration)} ({total_duration/60:.2f} 分钟)")
    print(f"时间范围: {format_time(first_time)} - {format_time(last_time)}")

    # 分析对话段落
    dialogs = analyze_segments(segments)

    print(f"\n识别到 {len(dialogs)} 个连麦/对话段落:\n")
    print("=" * 60)

    for i, dialog in enumerate(dialogs):
        duration = dialog['end'] - dialog['start']
        print(f"\n【连麦 {i+1}】")
        print(f"  开始时间: {format_time(dialog['start'])} ({dialog['start']:.2f}s)")
        print(f"  结束时间: {format_time(dialog['end'])} ({dialog['end']:.2f}s)")
        print(f"  持续时长: {format_time(duration)} ({duration/60:.2f} 分钟)")
        print(f"  参与说话人: {', '.join(dialog['speakers'])}")

    # 保存结果到文件
    output_file = file_path.replace('.json', '_dialog_segments.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_segments': len(segments),
            'total_duration': total_duration,
            'dialogs': dialogs
        }, f, ensure_ascii=False, indent=2)

    print(f"\n\n详细结果已保存到: {output_file}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_dialogs.py <json_file>")
        sys.exit(1)

    main(sys.argv[1])
