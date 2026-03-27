#!/usr/bin/env python3
"""
根据段落分析结果，创建子文件夹并分割字幕文件
"""

import json
import os
import sys
import re

def format_time(seconds):
    """将秒数格式化为 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def sanitize_filename(name):
    """清理文件名中的特殊字符"""
    # 移除或替换不安全字符
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip()
    return name

def create_segments(input_file, segments_file):
    """
    根据段落分析结果创建子文件
    """
    # 读取原始字幕
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    all_segments = data.get('segments', [])

    # 读取段落分析结果
    with open(segments_file, 'r', encoding='utf-8') as f:
        seg_data = json.load(f)

    segments = seg_data.get('segments', [])

    # 创建输出目录
    base_name = os.path.basename(input_file).replace('.json', '')
    output_dir = os.path.join(os.path.dirname(input_file), base_name + '_processed')
    os.makedirs(output_dir, exist_ok=True)

    print(f"创建输出目录: {output_dir}")
    print(f"总段落数: {len(segments)}")
    print()

    created_files = []
    call_counter = 0
    comment_counter = 0

    for i, seg in enumerate(segments):
        seg_type = seg['type']
        start_time = seg['start']
        end_time = seg['end']
        speakers = seg['speakers']

        # 计数器
        if seg_type == '连麦':
            call_counter += 1
            prefix = f"{i+1:02d}_连麦{call_counter}"
        elif seg_type == '评论':
            comment_counter += 1
            prefix = f"{i+1:02d}_评论{comment_counter}"
        elif seg_type == '开场白':
            prefix = f"{i+1:02d}_开场白"
        else:
            prefix = f"{i+1:02d}_{seg_type}"

        # 构建文件名
        duration_min = (end_time - start_time) / 60
        filename = f"{prefix}_{format_time(start_time).replace(':', '')}_{format_time(end_time).replace(':', '')}.json"
        filepath = os.path.join(output_dir, filename)

        # 提取该时间段内的字幕片段
        segment_data = [
            s for s in all_segments
            if s['start'] >= start_time and s['end'] <= end_time
        ]

        # 保存子文件
        output_data = {
            'segment_type': seg_type,
            'segment_index': i + 1,
            'start_time': start_time,
            'end_time': end_time,
            'duration': end_time - start_time,
            'speakers': speakers,
            'segments': segment_data
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        created_files.append({
            'index': i + 1,
            'type': seg_type,
            'filename': filename,
            'start': format_time(start_time),
            'end': format_time(end_time),
            'duration_min': duration_min,
            'segments_count': len(segment_data)
        })

        print(f"段落 {i+1}: {filename}")
        print(f"  类型: {seg_type}")
        print(f"  时间: {format_time(start_time)} - {format_time(end_time)}")
        print(f"  时长: {duration_min:.2f} 分钟")
        print(f"  片段数: {len(segment_data)}")
        print()

    # 创建索引文件
    index_file = os.path.join(output_dir, '_index.json')
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump({
            'source_file': os.path.basename(input_file),
            'output_directory': output_dir,
            'total_segments': len(segments),
            'files': created_files
        }, f, ensure_ascii=False, indent=2)

    print(f"索引文件: {index_file}")
    print(f"\n完成！共创建 {len(created_files)} 个子文件")

    return created_files

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python create_segment_files.py <input_json> <segments_json>")
        print("Example:")
        print("  python create_segment_files.py transcript.json transcript_final_segments.json")
        sys.exit(1)

    input_file = sys.argv[1]
    segments_file = sys.argv[2]

    create_segments(input_file, segments_file)
