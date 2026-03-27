#!/usr/bin/env python3
"""
合并 part JSON 文件按日期
- part01: 时间戳从 00:00:00 开始
- part02: 时间戳从 02:00:00 开始
- part03: 时间戳从 04:00:00 开始
以此类推
"""

import json
import os
import re
from pathlib import Path
from collections import defaultdict


def get_part_number(filename: str) -> int:
    """从文件名中提取 part 编号"""
    match = re.search(r'_part(\d+)\.json$', filename)
    if match:
        return int(match.group(1))
    return 0


def get_base_name(filename: str) -> str:
    """获取去掉 _partNN 后缀的基础文件名"""
    return re.sub(r'_part\d+\.json$', '.json', filename)


def get_time_offset(part_number: int) -> float:
    """根据 part 编号计算时间偏移（秒）
    part01 -> 0 秒
    part02 -> 7200 秒 (2小时)
    part03 -> 14400 秒 (4小时)
    """
    return (part_number - 1) * 2 * 3600  # 每个 part 2小时


def merge_json_files(json_files: list[str], output_path: str):
    """合并多个 JSON 文件"""
    all_segments = []
    all_speakers = set()

    # 按 part 编号排序
    sorted_files = sorted(json_files, key=lambda f: get_part_number(os.path.basename(f)))

    for json_file in sorted_files:
        part_num = get_part_number(os.path.basename(json_file))
        time_offset = get_time_offset(part_num)

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 处理 segments，添加时间偏移
        for segment in data.get('segments', []):
            new_segment = segment.copy()
            new_segment['start'] = segment['start'] + time_offset
            new_segment['end'] = segment['end'] + time_offset
            all_segments.append(new_segment)

        # 收集所有 speakers
        all_speakers.update(data.get('speakers', []))

    # 构建输出数据
    output_data = {
        'segments': all_segments,
        'speakers': sorted(list(all_speakers))
    }

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    return len(sorted_files), len(all_segments)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="合并 part JSON 文件按日期")
    parser.add_argument("--input-dir", type=str, default="data/02_audio_splits",
                        help="输入目录 (包含 _partNN.json 文件)")
    parser.add_argument("--output-dir", type=str, default="data/03_transcripts",
                        help="输出目录")
    parser.add_argument("--playlist", type=str, default=None,
                        help="播放列表子目录名，不填则处理 input-dir 下所有子目录")
    args = parser.parse_args()

    if args.playlist:
        pairs = [(Path(args.input_dir) / args.playlist, Path(args.output_dir) / args.playlist)]
    else:
        input_base = Path(args.input_dir)
        pairs = []
        for sub in sorted(input_base.iterdir()):
            if sub.is_dir():
                pairs.append((sub, Path(args.output_dir) / sub.name))

    for input_dir, output_dir in pairs:
        print(f"\n处理: {input_dir}")
        _merge_dir(input_dir, output_dir)


def _merge_dir(input_dir, output_dir):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    # 查找所有 JSON 文件
    json_files = list(input_dir.glob('*.json'))

    # 按基础名分组
    groups = defaultdict(list)
    for json_file in json_files:
        base_name = get_base_name(json_file.name)
        groups[base_name].append(str(json_file))

    print(f"找到 {len(json_files)} 个 JSON 文件，分为 {len(groups)} 组")
    print("-" * 60)

    # 处理每个分组
    for base_name, files in sorted(groups.items()):
        output_path = output_dir / base_name
        num_parts, num_segments = merge_json_files(files, str(output_path))
        print(f"合并 {num_parts} 个 part -> {base_name}")
        print(f"  共 {num_segments} 个 segments")

    print("-" * 60)
    print(f"完成！输出目录: {output_dir}")


if __name__ == '__main__':
    main()
