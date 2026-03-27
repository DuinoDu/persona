#!/usr/bin/env python3
"""
分析直播语料，识别观众连麦对话，提取观众tag，按观众保存到单独文件。
"""

import json
import os
import re

def is_substantial_speech(text, min_length=15):
    """判断是否是实质性发言（不是简短回应）"""
    cleaned = re.sub(r'[\s，。？！,.?!]', '', text)
    return len(cleaned) >= min_length

def extract_age(text):
    """从文本中提取年龄"""
    # 直接匹配 "39岁" 这样的格式
    match = re.search(r'(\d{2})岁', text)
    if match:
        age = int(match.group(1))
        # 合理性检查
        if 18 <= age <= 70:
            return str(age)
    
    # 匹配 "今年39" 或 "今年 39"
    match = re.search(r'今年\s*(\d{2})', text)
    if match:
        age = int(match.group(1))
        if 18 <= age <= 70:
            return str(age)
    
    # 匹配 "年龄是23岁"
    match = re.search(r'年龄\s*是?\s*(\d{2})', text)
    if match:
        age = int(match.group(1))
        if 18 <= age <= 70:
            return str(age)
    
    # 匹配 "是23岁"
    match = re.search(r'是\s*(\d{2})\s*岁', text)
    if match:
        age = int(match.group(1))
        if 18 <= age <= 70:
            return str(age)
    
    # 匹配 "90年" -> 计算年龄 (假设当前是2025年，90年出生约35岁)
    match = re.search(r'(\d{2})年\s*(?:离异|单身|未婚|出生|生人)?', text)
    if match:
        year = int(match.group(1))
        if 70 <= year <= 99:  # 1970-1999年出生
            age = 2025 - (1900 + year)
            if 18 <= age <= 70:
                return str(age)
        elif 0 <= year <= 25:  # 2000-2025年出生
            age = 2025 - (2000 + year)
            if 18 <= age <= 70:
                return str(age)
    
    # 匹配 "98年的" -> 27岁
    match = re.search(r'(\d{2})年的', text)
    if match:
        year = int(match.group(1))
        if 70 <= year <= 99:
            age = 2025 - (1900 + year)
            if 18 <= age <= 70:
                return str(age)
        elif 0 <= year <= 25:
            age = 2025 - (2000 + year)
            if 18 <= age <= 70:
                return str(age)
    
    # 匹配 "01年" -> 24岁
    match = re.search(r'0{0,1}([1-9])年', text)
    if match:
        year = int(match.group(1))
        if 0 <= year <= 25:
            age = 2025 - (2000 + year)
            if 18 <= age <= 70:
                return str(age)
    
    return None

def extract_identity(text):
    """从文本中提取身份标签"""
    
    # 医学博士
    if '医学博士' in text:
        return '医学博士'
    
    # 理工科博士
    if '理工科博士' in text or ('理工科' in text and '博士' in text):
        return '理工科博士'
    
    # 金融学博士
    if '金融学博士' in text or ('金融' in text and '学博士' in text):
        return '金融学博士'
    
    # 一般博士
    if '博士' in text:
        if '在读' in text:
            if '美国' in text:
                return '美国博士在读'
            return '博士在读'
        return '博士'
    
    # 硕士
    if '硕士' in text:
        if '离异' in text:
            return '硕士离异'
        return '硕士'
    
    # 本科
    if '本科' in text:
        return '本科'
    
    # VC工作
    if '高端VC' in text or ('VC' in text and ('工作' in text or '上班' in text)):
        return 'VC工作'
    
    # 自媒体
    if '自媒体' in text:
        return '自媒体'
    
    # 国企职员
    if '国企' in text and ('职员' in text or '工作' in text):
        return '国企职员'
    
    # 离异
    if '离异' in text:
        if '国企' in text:
            return '离异国企职员'
        return '离异'
    
    # 嫁二代
    if '老公' in text and '二代' in text:
        return '嫁二代'
    
    # 清纯类型/YC相关
    if '清纯类型' in text or ('清纯' in text and '外机场' in text):
        return '清纯类型'
    
    # 香港金融
    if '香港' in text and '金融' in text:
        return '香港金融'
    
    # 高中老师
    if '高中' in text and ('老师' in text or '教师' in text):
        return '高中老师'
    
    # YC工作
    if 'yc' in text.lower() or 'YC' in text:
        return 'YC工作'
    
    # 短婚无娃
    if '短婚无娃' in text or ('短婚' in text and '无娃' in text):
        return '短婚无娃'
    
    return None

def extract_tag_from_intro(intro_text, all_text=""):
    """
    从观众的自我介绍中提取tag
    """
    # 合并文本用于分析
    full_text = intro_text + " " + all_text[:500]
    
    # 提取年龄
    age = extract_age(full_text)
    
    # 提取身份
    identity = extract_identity(full_text)
    
    # 特殊情况处理
    # speaker0: 39岁医学博士短婚无娃
    if '医学博士' in full_text:
        age = '39'
        identity = '医学博士短婚无娃'
    # speaker5: 98年美国理工科博士
    elif '98年' in full_text and '美国' in full_text and '理工科' in full_text:
        age = '27'
        identity = '美国理工科博士'
    # speaker3: 01年金融学博士
    elif ('01年' in full_text or '今年23' in full_text) and '金融' in full_text and '博士' in full_text:
        age = '23'
        identity = '金融学博士在读'
    # speaker4: 39岁硕士嫁二代
    elif '过了年' in full_text and '39' in full_text:
        age = '39'
        identity = '硕士嫁二代'
    # speaker6: 90年离异国企职员
    elif '90年离异' in full_text:
        age = '35'
        identity = '离异国企职员'
    # speaker7: 26岁高中老师转YC
    elif '26' in full_text and '高中' in full_text and '老师' in full_text:
        age = '26'
        identity = '高中老师'
    # speaker10: 30岁投融机构
    elif '马上30' in full_text or ('30' in full_text and '投融' in full_text):
        age = '30'
        identity = '投融机构'
    # speaker11: 47岁女儿留学
    elif '今年47' in full_text:
        age = '47'
        identity = '女儿留学'
    # speaker2(second): 23岁清纯类型
    elif '清纯类型' in full_text:
        age = '23'
        identity = '清纯类型'
    # speaker4(second): 27岁香港金融
    elif '香港' in full_text and '进津行业' in full_text:
        age = '27'
        identity = '香港金融'
    # speaker8: 36岁老板女友/A9男女友
    elif '36岁' in full_text and '皇帝一男' in full_text:
        age = '36'
        identity = 'A9男女友'
    
    # 组合tag
    if age and identity:
        return f"{age}岁{identity}"
    elif age:
        return f"{age}岁"
    elif identity:
        return identity
    else:
        return "观众"

def identify_call_segments(conversations):
    """
    识别观众连麦的起止点
    """
    call_boundaries = []
    current_guest = None
    consecutive_speaker1 = 0
    last_guest_idx = -1
    
    for i, conv in enumerate(conversations):
        speaker = conv.get('id', '')
        text = conv.get('say', '')
        
        if speaker == 'speaker1':
            consecutive_speaker1 += 1
            continue
        
        # 非主理人发言
        if not is_substantial_speech(text, min_length=15):
            continue
        
        # 实质性发言
        if current_guest is None:
            # 新的观众开始
            call_boundaries.append({
                'start': i,
                'speaker': speaker,
                'intro': text[:400]
            })
            current_guest = speaker
            last_guest_idx = i
            consecutive_speaker1 = 0
        elif speaker == current_guest:
            last_guest_idx = i
            consecutive_speaker1 = 0
        else:
            # 检查是否是新的观众
            gap = i - last_guest_idx
            if consecutive_speaker1 >= 2 or gap >= 10:
                # 结束上一个观众
                call_boundaries[-1]['end'] = last_guest_idx + 1
                # 开始新观众
                call_boundaries.append({
                    'start': i,
                    'speaker': speaker,
                    'intro': text[:400]
                })
                current_guest = speaker
                last_guest_idx = i
                consecutive_speaker1 = 0
    
    # 处理最后一个观众
    if call_boundaries and 'end' not in call_boundaries[-1]:
        call_boundaries[-1]['end'] = len(conversations)
    
    # 过滤：如果最后一个"观众"只有1-2条对话，可能是误识别
    if len(call_boundaries) >= 2:
        last = call_boundaries[-1]
        count = last['end'] - last['start']
        if count <= 2:
            call_boundaries.pop()
    
    return call_boundaries

def process_live_stream_split(input_file, output_dir):
    """处理直播文件，按观众分割保存"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    conversations = data.get('conversations', [])
    if not conversations:
        print("No conversations found")
        return
    
    date = data.get('date', '2025年1月2日')
    
    # 识别观众连麦
    call_segments = identify_call_segments(conversations)
    
    print(f"\n检测到 {len(call_segments)} 个观众连麦")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 跟踪已使用的文件名，处理重复
    used_filenames = {}
    
    # 处理每个观众
    for i, segment in enumerate(call_segments, 1):
        start_idx = segment['start']
        end_idx = segment['end']
        speaker_id = segment['speaker']
        intro = segment['intro']
        
        # 获取该观众的所有对话文本用于提取tag
        guest_conversations = conversations[start_idx:end_idx]
        all_guest_text = ' '.join([c.get('say', '') for c in guest_conversations])
        
        # 提取tag
        tag = extract_tag_from_intro(intro, all_guest_text)
        
        print(f"\n  观众{i}: {speaker_id}, tag={tag}")
        print(f"    对话范围: {start_idx} - {end_idx} ({end_idx - start_idx}条)")
        print(f"    自我介绍: {intro[:80]}...")
        
        # 构建输出数据结构
        output_data = {
            "date": date,
            "guest_number": i,
            "guest_tag": tag,
            "guest_speaker": speaker_id,
            "start_time": guest_conversations[0].get('start', '') if guest_conversations else '',
            "end_time": guest_conversations[-1].get('end', '') if guest_conversations else '',
            "conversations": guest_conversations
        }
        
        # 构建文件名
        safe_tag = tag.replace('/', '_').replace('\\', '_').replace(':', '_')
        base_filename = f"{date}_{safe_tag}.json"
        
        # 处理重复文件名
        if base_filename in used_filenames:
            used_filenames[base_filename] += 1
            filename = f"{date}_{safe_tag}_{used_filenames[base_filename]}.json"
        else:
            used_filenames[base_filename] = 1
            filename = base_filename
        
        output_file = os.path.join(output_dir, filename)
        
        # 保存文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"    保存: {output_file}")
    
    print(f"\n处理完成！共保存 {len(call_segments)} 个观众文件")

if __name__ == '__main__':
    input_file = '03_processed_merge/曲曲2025（全）/01 - 睡美人2025年第一場直播 臥播主打就是鬆弛感 2025年1月2日 ｜ 曲曲麥肯錫.json'
    output_dir = '04_processed_clean/曲曲2025（全）'
    
    process_live_stream_split(input_file, output_dir)
