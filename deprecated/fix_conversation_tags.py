#!/usr/bin/env python3
"""
Fix conversation tags by analyzing the content more carefully.
"""

import json
import os
import re
import shutil

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_better_tag(segments):
    """Extract a better tag from conversation segments."""
    # Get all audience text
    audience_texts = []
    for seg in segments:
        if seg['speaker'] == '观众':
            audience_texts.append(seg['text'])

    full_text = ''.join(audience_texts[:50])  # First 50 segments

    print(f"Analyzing text (first 200 chars): {full_text[:200]}")

    # Extract age
    age = None
    age_patterns = [
        r'我今年(\d{2,3})[岁歲]',
        r'(\d{2,3})[岁歲]',
    ]
    for pattern in age_patterns:
        match = re.search(pattern, full_text)
        if match:
            age_num = int(match.group(1))
            if 18 <= age_num <= 99:
                age = f"{age_num}岁"
                break

    # Extract occupation/identity
    identity = None
    identity_patterns = [
        (r'(医学博士)', '医学博士'),
        (r'(历史学博士)', '历史学博士'),
        (r'(博士)', '博士'),
        (r'(硕士)', '硕士'),
        (r'(研究生)', '研究生'),
        (r'(创业)', '创业'),
        (r'(自己做生意)', '创业'),
        (r'(体制内)', '体制内'),
        (r'(公务员)', '公务员'),
        (r'(医生)', '医生'),
        (r'(律师)', '律师'),
        (r'(老师)', '老师'),
        (r'(教师)', '教师'),
        (r'(程序员)', '程序员'),
        (r'(工程师)', '工程师'),
    ]

    for pattern, label in identity_patterns:
        if re.search(pattern, full_text):
            identity = label
            break

    # Check for specific topics
    if not identity:
        if '辞职' in full_text or '做点小生意' in full_text:
            identity = '创业'
        elif '结婚' in full_text or '男朋友' in full_text or '女朋友' in full_text:
            identity = '婚恋咨询'
        elif '工作' in full_text and '职业' in full_text:
            identity = '职业咨询'

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(age)
    if identity:
        tag_parts.append(identity)

    if tag_parts:
        return ''.join(tag_parts)
    else:
        return '观众'

def fix_conversation_files(directory):
    """Fix all conversation files in the directory."""
    for filename in os.listdir(directory):
        if not filename.endswith('.json'):
            continue

        filepath = os.path.join(directory, filename)
        print(f"\n处理文件: {filename}")

        # Load the file
        data = load_json(filepath)
        segments = data.get('segments', [])

        # Skip very short conversations
        if len(segments) < 5:
            print(f"  跳过: 对话太短 ({len(segments)} 个片段)")
            continue

        # Extract better tag
        new_tag = extract_better_tag(segments)
        print(f"  新标签: {new_tag}")

        # Update the data
        data['guest_tag'] = new_tag

        # Generate new filename
        # Parse old filename: 2025年1月9日_003532-004814_观众.json
        match = re.match(r'(.+?)_(\d{6})-(\d{6})_(.+?)\.json', filename)
        if match:
            date_part, start_time, end_time, old_tag = match.groups()
            new_filename = f"{date_part}_{start_time}-{end_time}_{new_tag}.json"
            new_filepath = os.path.join(directory, new_filename)

            # Save with new filename
            save_json(new_filepath, data)
            print(f"  保存为: {new_filename}")

            # Remove old file if different
            if new_filename != filename:
                os.remove(filepath)
                print(f"  删除旧文件: {filename}")
        else:
            # Just update the existing file
            save_json(filepath, data)
            print(f"  更新文件: {filename}")

if __name__ == '__main__':
    directory = '07_conversations/曲曲2025（全）/20250109'
    fix_conversation_files(directory)
    print("\n完成!")
