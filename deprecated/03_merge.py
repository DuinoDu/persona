#!/usr/bin/env python3
"""
按日期合并JSON文件
- 同一天的part文件合并为一个
- 调整时间戳为连续的时间
- 累加duration
"""

import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple


def time_to_seconds(time_str: str) -> int:
    """将时间字符串 HH:MM:SS 转换为秒数"""
    parts = time_str.strip().split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + int(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + int(s)
    else:
        return int(parts[0])


def seconds_to_time(seconds: int) -> str:
    """将秒数转换为 HH:MM:SS 格式"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def extract_date_from_filename(filename: str) -> str:
    """从文件名中提取日期，格式: 2025年1月2日"""
    # 匹配 "2025年1月2日" 这样的格式
    match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', filename)
    if match:
        return match.group(1)
    return None


def extract_part_number(filename: str) -> int:
    """从文件名中提取part序号"""
    match = re.search(r'_part(\d+)\.json$', filename)
    if match:
        return int(match.group(1))
    return 0


def extract_title_prefix(filename: str) -> str:
    """提取标题前缀（去掉part部分）"""
    # 去掉 _partXX.json 后缀
    return re.sub(r'_part\d+\.json$', '', filename)


def load_json_files(input_dir: str) -> Dict[str, List[Tuple[str, dict, int]]]:
    """
    加载所有JSON文件并按日期分组
    返回: {日期: [(文件名, JSON数据, part序号), ...]}
    """
    files_by_date = {}
    input_path = Path(input_dir)
    
    for json_file in input_path.rglob('*.json'):
        # 跳过隐藏文件
        if json_file.name.startswith('.'):
            continue
        
        date = extract_date_from_filename(json_file.name)
        if not date:
            continue
        
        part_num = extract_part_number(json_file.name)
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 计算相对路径（用于保留目录结构）
        rel_dir = json_file.parent.relative_to(input_path)
        
        if date not in files_by_date:
            files_by_date[date] = []
        
        files_by_date[date].append({
            'file': json_file,
            'rel_dir': rel_dir,
            'data': data,
            'part_num': part_num,
            'title_prefix': extract_title_prefix(json_file.name)
        })
    
    return files_by_date


def merge_conversations(files_info: List[dict]) -> Tuple[int, List[dict]]:
    """
    合并多个文件的conversations，调整时间戳
    返回: (总时长, 合并后的conversations)
    """
    # 按part序号排序
    files_info = sorted(files_info, key=lambda x: x['part_num'])
    
    total_duration = 0
    merged_conversations = []
    time_offset = 0  # 时间偏移量（秒）
    
    for file_info in files_info:
        data = file_info['data']
        duration = data.get('duration', 0)
        
        for conv in data.get('conversations', []):
            # 调整时间戳
            start_sec = time_to_seconds(conv['start']) + time_offset
            end_sec = time_to_seconds(conv['end']) + time_offset
            
            merged_conversations.append({
                'id': conv['id'],
                'say': conv['say'],
                'start': seconds_to_time(start_sec),
                'end': seconds_to_time(end_sec)
            })
        
        time_offset += duration
        total_duration += duration
    
    return total_duration, merged_conversations


def merge_files_by_date(input_dir: str, output_dir: str):
    """
    按日期合并JSON文件
    """
    # 加载文件
    files_by_date = load_json_files(input_dir)
    
    if not files_by_date:
        print("未找到需要合并的JSON文件")
        return
    
    output_base = Path(output_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    
    merged_count = 0
    
    for date, files_info in files_by_date.items():
        if len(files_info) < 2:
            # 只有一个文件，也需要复制到输出目录（可选）
            # 这里选择也复制过去，保持完整性
            pass
        
        # 获取共同的相对目录
        rel_dir = files_info[0]['rel_dir']
        title_prefix = files_info[0]['title_prefix']
        
        # 创建输出目录
        out_dir = output_base / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 合并conversations
        total_duration, merged_conversations = merge_conversations(files_info)
        
        # 构建输出文件名（去掉part后缀）
        output_filename = f"{title_prefix}.json"
        output_path = out_dir / output_filename
        
        # 构建结果
        result = {
            'title': title_prefix,
            'date': date,
            'duration': total_duration,
            'parts_count': len(files_info),
            'conversations': merged_conversations
        }
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"✓ {date}: 合并 {len(files_info)} 个文件 -> {output_path}")
        print(f"  总时长: {total_duration} 秒 ({seconds_to_time(total_duration)})")
        print(f"  对话数: {len(merged_conversations)}")
        merged_count += 1
    
    print(f"\n合并完成！共处理 {merged_count} 个日期组")


def main():
    parser = argparse.ArgumentParser(description='按日期合并JSON文件')
    parser.add_argument('-i', '--input', default='02_processed', help='输入目录 (默认: 02_processed)')
    parser.add_argument('-o', '--output', default='03_processed_merge', help='输出目录 (默认: 03_processed_merge)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"错误: 输入目录不存在: {args.input}")
        return
    
    merge_files_by_date(args.input, args.output)


if __name__ == '__main__':
    main()
