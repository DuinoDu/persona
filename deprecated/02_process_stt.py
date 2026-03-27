#!/usr/bin/env python3
"""
STT文本处理工具：合并同一人连续说话内容，输出JSON格式
"""

import os
import re
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional


@dataclass
class Conversation:
    id: str
    say: str
    start: str
    end: str


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


def parse_stt_file(file_path: str) -> tuple:
    """
    解析STT文本文件
    返回: (duration_seconds, conversations)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # 解析元信息
    duration = 0
    for line in lines[:10]:  # 只检查前10行
        if line.startswith('# 时长:'):
            match = re.search(r'(\d+)\s*秒', line)
            if match:
                duration = int(match.group(1))
            break
    
    # 解析对话片段
    conversations = []
    current_speaker = None
    current_start = None
    current_end = None
    current_content = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 匹配带speaker的行: [speaker1] 00:00:00 - 00:00:03
        speaker_match = re.match(r'\[(speaker\d+)\]\s+(\d+:\d+:\d+)\s+-\s+(\d+:\d+:\d+)', line)
        if speaker_match:
            # 保存之前的对话
            if current_speaker and current_content:
                conversations.append({
                    'speaker': current_speaker,
                    'start': current_start,
                    'end': current_end,
                    'content': ' '.join(current_content)
                })
            
            current_speaker = speaker_match.group(1)
            current_start = speaker_match.group(2)
            current_end = speaker_match.group(3)
            current_content = []
            
            # 读取内容（下一行）
            i += 1
            if i < len(lines):
                content_line = lines[i].strip()
                if content_line and not content_line.startswith('[') and not content_line.startswith('#'):
                    current_content.append(content_line)
        
        # 匹配只有时间戳的行: [00:00:03 - 00:00:04]
        elif line.startswith('[') and 'speaker' not in line:
            time_match = re.match(r'\[(\d+:\d+:\d+)\s+-\s+(\d+:\d+:\d+)\]', line)
            if time_match and current_speaker:
                # 延续当前speaker，更新时间
                current_end = time_match.group(2)
                
                # 读取内容（下一行）
                i += 1
                if i < len(lines):
                    content_line = lines[i].strip()
                    if content_line and not content_line.startswith('[') and not content_line.startswith('#'):
                        current_content.append(content_line)
        
        i += 1
    
    # 保存最后一个对话
    if current_speaker and current_content:
        conversations.append({
            'speaker': current_speaker,
            'start': current_start,
            'end': current_end,
            'content': ' '.join(current_content)
        })
    
    return duration, conversations


def merge_consecutive_conversations(conversations: List[dict]) -> List[Conversation]:
    """
    合并同一人连续说话的内容
    """
    if not conversations:
        return []
    
    merged = []
    current = {
        'speaker': conversations[0]['speaker'],
        'start': conversations[0]['start'],
        'end': conversations[0]['end'],
        'content': [conversations[0]['content']]
    }
    
    for conv in conversations[1:]:
        if conv['speaker'] == current['speaker']:
            # 同一人，合并
            current['end'] = conv['end']
            current['content'].append(conv['content'])
        else:
            # 不同人，保存当前并新建
            merged.append(Conversation(
                id=current['speaker'],
                say=' '.join(current['content']),
                start=current['start'],
                end=current['end']
            ))
            current = {
                'speaker': conv['speaker'],
                'start': conv['start'],
                'end': conv['end'],
                'content': [conv['content']]
            }
    
    # 保存最后一个
    merged.append(Conversation(
        id=current['speaker'],
        say=' '.join(current['content']),
        start=current['start'],
        end=current['end']
    ))
    
    return merged


def process_file(input_file: str, output_base_dir: str) -> str:
    """
    处理单个STT文件，输出JSON
    返回输出文件路径
    """
    # 解析文件
    duration, raw_conversations = parse_stt_file(input_file)
    
    # 合并连续说话
    merged_conversations = merge_consecutive_conversations(raw_conversations)
    
    # 构建输出路径，保持目录结构
    input_path = Path(input_file)
    rel_path = input_path.relative_to('01_stt') if str(input_file).startswith('01_stt') else input_path.name
    output_dir = Path(output_base_dir) / rel_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 输出文件名
    output_file = output_dir / (input_path.stem + '.json')
    
    # 构建JSON数据
    result = {
        'title': input_path.stem,
        'duration': duration,
        'conversations': [asdict(c) for c in merged_conversations]
    }
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return str(output_file)


def process_directory(input_dir: str, output_dir: str) -> List[str]:
    """
    批量处理目录下的所有txt文件
    """
    output_files = []
    input_path = Path(input_dir)
    
    for txt_file in input_path.rglob('*.txt'):
        # 跳过隐藏文件
        if txt_file.name.startswith('.'):
            continue
        
        try:
            output_file = process_file(str(txt_file), output_dir)
            output_files.append(output_file)
            print(f"✓ 处理完成: {txt_file} -> {output_file}")
        except Exception as e:
            print(f"✗ 处理失败: {txt_file} - {e}")
    
    return output_files


def main():
    parser = argparse.ArgumentParser(description='STT文本处理工具')
    parser.add_argument('input', help='输入文件或目录')
    parser.add_argument('-o', '--output', default='02_processed', help='输出目录 (默认: 02_processed)')
    
    args = parser.parse_args()
    
    if os.path.isfile(args.input):
        output_file = process_file(args.input, args.output)
        print(f"\n处理完成！输出文件: {output_file}")
    elif os.path.isdir(args.input):
        output_files = process_directory(args.input, args.output)
        print(f"\n批量处理完成！共处理 {len(output_files)} 个文件")
    else:
        print(f"错误: 输入路径不存在: {args.input}")


if __name__ == '__main__':
    main()
