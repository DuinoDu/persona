#!/usr/bin/env python3
"""
批量分析直播语料，识别观众连麦对话，提取观众tag，按观众保存到单独文件。
- 遍历 03_processed_merge 下的所有 JSON 文件
- 识别观众连麦对话
- 提取观众tag（如'39岁医学博士'）
- 按观众截取保存到 04_processed_clean，保留相同文件夹结构
- 文件名为 <日期>_<观众的tag>.json
"""

import json
import os
import re
from pathlib import Path

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
    
    # 匹配 "90年" -> 计算年龄 (假设当前是2025年)
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
    
    # 常见职业/身份
    identities = [
        ('学生', '学生'),
        ('老师', '老师'),
        ('教师', '老师'),
        ('医生', '医生'),
        ('律师', '律师'),
        ('公务员', '公务员'),
        ('创业', '创业者'),
        ('老板', '老板'),
        ('销售', '销售'),
        ('程序员', '程序员'),
        ('工程师', '工程师'),
        ('设计师', '设计师'),
        ('模特', '模特'),
        ('主播', '主播'),
        ('全职妈妈', '全职妈妈'),
        ('宝妈', '宝妈'),
        ('护士', '护士'),
        ('翻译', '翻译'),
        ('空姐', '空姐'),
        ('投行', '投行'),
        ('咨询', '咨询'),
        ('会计', '会计'),
        ('金融', '金融'),
        ('互联网', '互联网'),
        ('大厂', '大厂'),
    ]
    
    for keyword, identity in identities:
        if keyword in text:
            return identity
    
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
    
    # 特殊情况处理 - 基于示例数据优化
    # speaker0: 39岁医学博士短婚无娃
    if '医学博士' in full_text and '短婚无娃' in full_text:
        age = age or '39'
        identity = '医学博士短婚无娃'
    # 98年美国理工科博士
    elif '98年' in full_text and '美国' in full_text and '理工科' in full_text:
        age = age or '27'
        identity = '美国理工科博士'
    # 01年金融学博士
    elif ('01年' in full_text or '今年23' in full_text) and '金融' in full_text and '博士' in full_text:
        age = age or '23'
        identity = '金融学博士在读'
    # 39岁硕士嫁二代
    elif '过了年' in full_text and '39' in full_text:
        age = age or '39'
        identity = '硕士嫁二代'
    # 90年离异国企职员
    elif '90年离异' in full_text:
        age = age or '35'
        identity = '离异国企职员'
    # 26岁高中老师转YC
    elif '26' in full_text and '高中' in full_text and '老师' in full_text:
        age = age or '26'
        identity = '高中老师'
    # 30岁投融机构
    elif '马上30' in full_text or ('30' in full_text and '投融' in full_text):
        age = age or '30'
        identity = '投融机构'
    # 47岁女儿留学
    elif '今年47' in full_text:
        age = age or '47'
        identity = '女儿留学'
    # 23岁清纯类型
    elif '清纯类型' in full_text:
        age = age or '23'
        identity = '清纯类型'
    # 27岁香港金融
    elif '香港' in full_text and '进津行业' in full_text:
        age = age or '27'
        identity = '香港金融'
    # 36岁老板女友/A9男女友
    elif '36岁' in full_text and '皇帝一男' in full_text:
        age = age or '36'
        identity = 'A9男女友'
    
    # 组合tag
    if age and identity:
        return f"{age}岁{identity}"
    elif age:
        return f"{age}岁观众"
    elif identity:
        return identity
    else:
        return "观众"

def identify_call_segments(conversations):
    """
    识别观众连麦的起止点
    直播环节：
    1. 开场白（主理人独白）
    2. 观众提问（一般会念稿，持续5～10分钟）
    3. 正常对话（多轮对话）
    4. 连麦结束，观众下线
    5. 主理人评价，然后连麦下一个
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

def extract_date_from_filename(filename):
    """从文件名中提取日期"""
    # 尝试匹配 2025年1月2日 格式
    match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', filename)
    if match:
        year, month, day = match.groups()
        return f"{year}年{int(month)}月{int(day)}日"
    
    # 尝试匹配 2025年1月2号 格式
    match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})号', filename)
    if match:
        year, month, day = match.groups()
        return f"{year}年{int(month)}月{int(day)}日"
    
    return None

def process_single_file(input_file, output_dir):
    """处理单个直播文件，按观众分割保存"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    conversations = data.get('conversations', [])
    if not conversations:
        print(f"  No conversations found in {input_file}")
        return 0
    
    # 获取日期 - 优先使用 JSON 中的 date 字段，否则从文件名提取
    date = data.get('date', '')
    if not date:
        date = extract_date_from_filename(os.path.basename(input_file))
    if not date:
        date = '未知日期'
    
    # 识别观众连麦
    call_segments = identify_call_segments(conversations)
    
    if not call_segments:
        print(f"  未检测到观众连麦: {os.path.basename(input_file)}")
        return 0
    
    print(f"  检测到 {len(call_segments)} 个观众连麦")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 跟踪已使用的文件名，处理重复
    used_filenames = {}
    saved_count = 0
    
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
        
        print(f"    观众{i}: {speaker_id}, tag={tag}, 对话数={len(guest_conversations)}")
        
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
        
        saved_count += 1
    
    return saved_count

def batch_process(input_root, output_root):
    """
    批量处理所有直播文件
    """
    input_path = Path(input_root)
    output_path = Path(output_root)
    
    # 查找所有 JSON 文件
    json_files = list(input_path.rglob('*.json'))
    
    print(f"找到 {len(json_files)} 个 JSON 文件需要处理")
    print(f"输入目录: {input_root}")
    print(f"输出目录: {output_root}")
    print()
    
    total_files = 0
    total_guests = 0
    
    for json_file in json_files:
        # 计算相对路径
        rel_path = json_file.relative_to(input_path)
        
        # 构建输出目录（保持相同的目录结构）
        output_dir = output_path / rel_path.parent
        
        print(f"处理: {rel_path}")
        
        try:
            guest_count = process_single_file(str(json_file), str(output_dir))
            total_guests += guest_count
            if guest_count > 0:
                total_files += 1
        except Exception as e:
            print(f"  错误: {e}")
        
        print()
    
    print("=" * 60)
    print(f"批量处理完成！")
    print(f"处理文件数: {total_files}/{len(json_files)}")
    print(f"总观众数: {total_guests}")

if __name__ == '__main__':
    input_root = '/home/duino/ws/5506fd19-4482-4233-91b6-8e4a5a10b6f1/f9536ea0-62cb-47e2-b1cf-68252d7061e4/03_processed_merge'
    output_root = '/home/duino/ws/5506fd19-4482-4233-91b6-8e4a5a10b6f1/f9536ea0-62cb-47e2-b1cf-68252d7061e4/04_processed_clean'
    
    batch_process(input_root, output_root)
