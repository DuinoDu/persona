#!/usr/bin/env python3
"""
修复已分割文件的格式问题，确保符合schema要求
"""

import json
import os
from pathlib import Path

def fix_speaker_ids(speaker_ids):
    """修复重复的speaker_ids，确保只有host和/或guest"""
    unique_ids = []
    if 'host' in speaker_ids:
        unique_ids.append('host')
    if 'guest' in speaker_ids:
        unique_ids.append('guest')
    return unique_ids

def process_file(filepath):
    """处理单个文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 修复speaker_ids
    if 'meta' in data and 'speaker_ids' in data['meta']:
        original = data['meta']['speaker_ids']
        fixed = fix_speaker_ids(original)
        if original != fixed:
            print(f"  修复 {os.path.basename(filepath)}: {original} -> {fixed}")
            data['meta']['speaker_ids'] = fixed

    # 确保sentences中的speaker_id和speaker_name正确
    if 'sentences' in data:
        for sent in data['sentences']:
            if sent['speaker_id'] == 'unknown':
                # 尝试从speaker_names推断
                if 'host' in data['meta'].get('speaker_names', {}):
                    sent['speaker_id'] = 'host'
                    sent['speaker_name'] = data['meta']['speaker_names']['host']

    # 保存修复后的文件
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return True

def main():
    processed_dir = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/31 - 未删减修复版 2024年06月06日  #曲曲大女人 #曲曲麦肯锡  #曲曲 #曲曲直播 #美人解忧铺 #金贵的关系_processed'

    if not os.path.exists(processed_dir):
        print(f"目录不存在: {processed_dir}")
        return

    json_files = sorted([f for f in os.listdir(processed_dir) if f.endswith('.json')])
    print(f"找到 {len(json_files)} 个JSON文件")

    for fname in json_files:
        filepath = os.path.join(processed_dir, fname)
        process_file(filepath)

    print("\n修复完成!")

if __name__ == '__main__':
    main()
EOF
