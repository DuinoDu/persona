#!/usr/bin/env python3
"""
Improve guest tags for existing conversations by re-analyzing the content.
"""

import json
import os
import re

def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_better_tag(segments):
    """Extract a better guest tag from conversation segments."""
    # Combine more text for better analysis
    intro_text = ' '.join([seg['text'] for seg in segments[:min(30, len(segments))]])

    # Extract age
    age_matches = re.findall(r'(\d{2})岁', intro_text)
    age = None
    if age_matches:
        # Filter out unrealistic ages and take the first reasonable one
        for a in age_matches:
            if 18 <= int(a) <= 60:
                age = a
                break

    # Extract education
    education = None
    if '博士' in intro_text:
        education = '博士'
    elif '硕士' in intro_text:
        education = '硕士'
    elif '本科' in intro_text:
        education = '本科'

    # Extract profession/keywords
    profession = None
    profession_map = {
        '医生': '医生', '医学': '医学',
        '工程师': '工程师', '程序员': '程序员',
        '教师': '教师', '老师': '老师', '高校': '高校老师',
        '体制内': '体制内',
        '律师': '律师',
        '设计师': '设计师',
        '产品': '产品',
        '运营': '运营',
        '销售': '销售',
        '创业': '创业',
        '金融': '金融',
        '咨询': '咨询',
        '主播': '主播', '娱乐主播': '主播',
        '瑜伽': '瑜伽',
        '经纪': '经纪',
        '博主': '博主',
    }

    for key, value in profession_map.items():
        if key in intro_text:
            profession = value
            break

    # Build tag
    tag_parts = []
    if age:
        tag_parts.append(f"{age}岁")
    if education:
        tag_parts.append(education)
    if profession:
        tag_parts.append(profession)

    if not tag_parts:
        # Fallback
        tag_parts.append('观众')

    return '_'.join(tag_parts)

def main():
    conv_dir = "/home/duino/ws/ququ/process_youtube/07_conversations/20250123"

    files = sorted([f for f in os.listdir(conv_dir) if f.endswith('.json')])

    print(f"Processing {len(files)} conversations...")
    print()

    updated_count = 0

    for filename in files:
        filepath = os.path.join(conv_dir, filename)
        data = load_json(filepath)

        old_tag = data['metadata']['guest_tag']
        segments = data['segments']

        # Extract better tag
        new_tag = extract_better_tag(segments)

        if new_tag != old_tag:
            print(f"Updating: {filename}")
            print(f"  Old tag: {old_tag}")
            print(f"  New tag: {new_tag}")

            # Update metadata
            data['metadata']['guest_tag'] = new_tag

            # Create new filename
            parts = filename.split('_')
            parts[-1] = f"{new_tag}.json"
            new_filename = '_'.join(parts)
            new_filepath = os.path.join(conv_dir, new_filename)

            # Save with new filename
            save_json(new_filepath, data)

            # Remove old file if name changed
            if new_filename != filename:
                os.remove(filepath)

            updated_count += 1
            print(f"  Saved as: {new_filename}")
            print()

    print(f"\nUpdated {updated_count} conversations")
    print("Done!")

if __name__ == "__main__":
    main()
