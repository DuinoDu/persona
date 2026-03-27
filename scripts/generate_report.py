#!/usr/bin/env python3
"""
生成处理结果总结报告
"""

import json
import os
import sys
from pathlib import Path

def format_duration(seconds):
    """格式化时长为 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def generate_report(processed_dir):
    """生成处理结果报告"""

    # 读取索引文件
    index_file = os.path.join(processed_dir, '_index.json')
    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    files = index_data.get('files', [])

    # 统计信息
    total_segments = len(files)
    intro_count = sum(1 for f in files if '开场白' in f['filename'])
    call_count = sum(1 for f in files if '连麦' in f['filename'])
    comment_count = sum(1 for f in files if '评论' in f['filename'])

    # 计算总时长
    total_duration = sum(f.get('duration_min', 0) for f in files)

    # 生成报告
    report = []
    report.append("=" * 80)
    report.append("直播字幕处理结果报告")
    report.append("=" * 80)
    report.append("")
    report.append(f"源文件: {index_data.get('source_file', 'N/A')}")
    report.append(f"输出目录: {processed_dir}")
    report.append("")
    report.append("-" * 80)
    report.append("统计信息")
    report.append("-" * 80)
    report.append(f"总段落数: {total_segments}")
    report.append(f"总时长: {format_duration(total_duration * 60)} ({total_duration:.2f} 分钟)")
    report.append("")
    report.append(f"开场白: {intro_count} 个")
    report.append(f"连麦次数: {call_count} 次")
    report.append(f"评论段落: {comment_count} 个")
    report.append("")
    report.append("-" * 80)
    report.append("详细段落列表")
    report.append("-" * 80)
    report.append("")

    call_counter = 0
    comment_counter = 0

    for i, file_info in enumerate(files):
        filename = file_info.get('filename', '')
        duration = file_info.get('duration_min', 0)
        seg_count = file_info.get('segments_count', 0)

        if '开场白' in filename:
            title = "【开场白】"
        elif '连麦' in filename:
            call_counter += 1
            title = f"【连麦 {call_counter}】"
        elif '评论' in filename:
            comment_counter += 1
            title = f"【评论 {comment_counter}】"
        else:
            title = f"【段落 {i+1}】"

        report.append(f"段落 {i+1}: {title}")
        report.append(f"  文件: {filename}")
        report.append(f"  时长: {format_duration(duration * 60)} ({duration:.2f} 分钟)")
        report.append(f"  原始片段数: {seg_count}")
        report.append("")

    report.append("=" * 80)
    report.append("处理完成！")
    report.append("=" * 80)

    return "\n".join(report)

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_report.py <processed_directory>")
        print("Example:")
        print("  python generate_report.py /path/to/processed/")
        sys.exit(1)

    processed_dir = sys.argv[1]

    if not os.path.exists(processed_dir):
        print(f"错误: 目录不存在: {processed_dir}")
        sys.exit(1)

    report = generate_report(processed_dir)

    # 保存报告
    report_file = os.path.join(processed_dir, '_report.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f"\n报告已保存到: {report_file}")

if __name__ == '__main__':
    main()
