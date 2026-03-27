#!/usr/bin/env python3
"""
处理18号文件的脚本
- 识别连麦结构
- 分割成子文件
- 识别说话人并分句
"""

import json
import os
from datetime import timedelta

def load_transcript(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['segments']

def format_time(seconds):
    """将秒数转换为 HH:MM:SS.ff 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    frac = int((seconds - int(seconds)) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{frac:02d}"

def format_duration(seconds):
    """格式化时长"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}分{secs}秒"

def identify_structure(segments):
    """
    识别直播结构
    基于主播独白和嘉宾交替说话的模式
    """
    
    structure = []
    
    # 1. 找到开场结束点（主播说"开始连麦"）
    opening_end = None
    for seg in segments:
        if '开始连麦' in seg.get('text', '') and seg['speaker'] == 'SPEAKER_01':
            opening_end = seg['end']
            break
    
    if opening_end is None:
        # 如果没找到，用第一个非主播发言作为开场结束
        for seg in segments:
            if seg['speaker'] not in ['SPEAKER_01', 'UNKNOWN']:
                opening_end = seg['start']
                break
    
    structure.append({
        'kind': 'opening',
        'start': 0,
        'end': opening_end,
        'guest': None,
        'persona': ''
    })
    
    # 2. 识别连麦时间段
    # 策略：找到主播+嘉宾交替说话的时间段
    
    all_speakers = set(s['speaker'] for s in segments)
    guests = [s for s in all_speakers if s not in ['SPEAKER_01', 'UNKNOWN']]
    
    current_time = opening_end
    
    # 基于时间窗口分析，识别主要的连麦时间段
    # 这里使用简化的方法：每个嘉宾的主要连麦时间
    
    for guest in sorted(guests):
        guest_segs = [s for s in segments if s['speaker'] == guest and s['start'] >= current_time - 300]
        if not guest_segs:
            continue
        
        # 找到这个嘉宾的主要连麦时间
        first_seg = min(guest_segs, key=lambda s: s['start'])
        last_seg = max(guest_segs, key=lambda s: s['end'])
        
        # 估算连麦开始和结束时间
        call_start = first_seg['start'] - 10  # 稍微提前一点
        call_end = last_seg['end']
        
        # 确定人设
        persona = ""
        if guest == 'SPEAKER_00':
            # 从文本中提取人设信息
            for s in segments:
                if s['speaker'] == guest and '岁' in s.get('text', ''):
                    text = s.get('text', '')
                    if '25' in text or '大二' in text:
                        persona = "25岁大二女生"
                        break
            if not persona:
                persona = "25岁大二女生"
        
        structure.append({
            'kind': 'call',
            'start': call_start,
            'end': call_end,
            'guest': guest,
            'persona': persona
        })
        
        current_time = call_end
    
    return structure

def split_into_sentences(text, min_length=5):
    """
    将文本分割成句子
    基于标点符号
    """
    import re
    
    # 定义句子结束标点
    sentence_endings = r'[。！？；.!?;]'
    
    # 分割句子
    parts = re.split(f'({sentence_endings})', text)
    
    sentences = []
    current = ""
    
    for i, part in enumerate(parts):
        if not part:
            continue
        current += part
        if re.match(sentence_endings, part) or i == len(parts) - 1:
            if len(current.strip()) >= min_length:
                sentences.append(current.strip())
            current = ""
    
    if current.strip() and len(current.strip()) >= min_length:
        sentences.append(current.strip())
    
    return sentences if sentences else [text]

def merge_segments_by_speaker(segments, max_gap=0.5):
    """
    将同一speaker的连续segment合并
    """
    if not segments:
        return []
    
    merged = []
    current = {
        'speaker': segments[0]['speaker'],
        'start': segments[0]['start'],
        'end': segments[0]['end'],
        'text': segments[0].get('text', '')
    }
    
    for seg in segments[1:]:
        if seg['speaker'] == current['speaker'] and seg['start'] - current['end'] <= max_gap:
            # 合并
            current['end'] = seg['end']
            if seg.get('text'):
                current['text'] += ' ' + seg['text']
        else:
            merged.append(current)
            current = {
                'speaker': seg['speaker'],
                'start': seg['start'],
                'end': seg['end'],
                'text': seg.get('text', '')
            }
    
    merged.append(current)
    return merged

def process_section(segments, section_info, section_index, input_file):
    """
    处理一个段落（开场、连麦、评论）
    返回符合schema格式的数据
    """
    kind = section_info['kind']
    start_time = section_info['start']
    end_time = section_info['end']
    guest = section_info.get('guest')
    persona = section_info.get('persona', '')
    
    # 提取该时间段的segments
    section_segments = [s for s in segments if start_time <= s['start'] < end_time]
    
    if not section_segments:
        return None
    
    # 合并同一speaker的segment
    merged = merge_segments_by_speaker(section_segments)
    
    # 构建sentences
    sentences = []
    speaker_map = {'SPEAKER_01': 'host'}
    if guest:
        speaker_map[guest] = 'guest'
    
    speaker_names = {'host': '曲曲'}
    if guest:
        if persona:
            speaker_names['guest'] = f"嘉宾({persona})"
        else:
            speaker_names['guest'] = '嘉宾'
    
    for seg in merged:
        speaker = seg['speaker']
        if speaker not in speaker_map:
            continue
        
        speaker_id = speaker_map[speaker]
        speaker_name = speaker_names[speaker_id]
        
        text = seg.get('text', '').strip()
        if not text:
            continue
        
        # 分句
        for sentence in split_into_sentences(text):
            sentences.append({
                'speaker_id': speaker_id,
                'speaker_name': speaker_name,
                'start': seg['start'],
                'end': seg['end'],
                'text': sentence
            })
    
    # 构建meta
    kind_enum = kind if kind in ['opening', 'call', 'comment'] else 'comment'
    
    meta = {
        'source_file': input_file,
        'index': section_index,
        'kind': kind_enum,
        'persona': persona,
        'title': f"{kind}_{section_index:02d}",
        'start': start_time,
        'end': end_time,
        'start_ts': format_time(start_time),
        'end_ts': format_time(end_time),
        'raw_segment_count': len(section_segments),
        'speaker_ids': list(speaker_map.values()),
        'speaker_names': speaker_names,
        'sentence_count': len(sentences),
        'notes': ''
    }
    
    return {
        'meta': meta,
        'sentences': sentences
    }

# 主处理逻辑
def main():
    # 加载数据
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/18 - 曲曲大女人 2024年04月19日 我是不完美主义者 高清分章节完整版 #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺.json'
    segments = load_transcript(input_file)
    
    # 创建输出目录
    base_name = os.path.basename(input_file).replace('.json', '')
    output_dir = f'/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/{base_name}_分段'
    os.makedirs(output_dir, exist_ok=True)
    
    # 识别结构
    structure = identify_structure(segments)
    
    print(f"识别出 {len(structure)} 个段落:\n")
    for i, s in enumerate(structure):
        kind = s['kind']
        start_m = int(s['start'] // 60)
        start_s = int(s['start'] % 60)
        end_m = int(s['end'] // 60)
        end_s = int(s['end'] % 60)
        guest = s.get('guest', '')
        persona = s.get('persona', '')
        
        guest_info = f" ({guest}" if guest else ""
        if persona:
            guest_info += f", {persona}"
        if guest:
            guest_info += ")"
        
        print(f"{i}. {kind}: {start_m}:{start_s:02d} - {end_m}:{end_s:02d}{guest_info}")
    
    # 处理每个段落
    print("\n\n开始处理段落...")
    
    output_files = []
    
    for i, section_info in enumerate(structure):
        print(f"\n处理段落 {i} ({section_info['kind']})...")
        
        result = process_section(segments, section_info, i, input_file)
        
        if result and result['sentences']:
            # 生成文件名
            kind = section_info['kind']
            guest = section_info.get('guest', '')
            persona = section_info.get('persona', '')
            
            if kind == 'opening':
                filename = f"{i:02d}_开场.json"
            elif kind == 'comment':
                filename = f"{i:02d}_评论.json"
            else:  # call
                if persona:
                    safe_persona = persona.replace("岁", "").replace("女生", "").replace(" ", "_")
                    filename = f"{i:02d}_{safe_persona}_连麦.json"
                elif guest:
                    filename = f"{i:02d}_{guest}_连麦.json"
                else:
                    filename = f"{i:02d}_连麦.json"
            
            output_path = os.path.join(output_dir, filename)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"  已保存: {filename}")
            print(f"  - 句子数: {len(result['sentences'])}")
            print(f"  - 时长: {format_duration(result['meta']['end'] - result['meta']['start'])}")
            
            output_files.append(filename)
        else:
            print(f"  跳过 (无有效句子)")
    
    print(f"\n\n处理完成! 共生成 {len(output_files)} 个文件:")
    for f in output_files:
        print(f"  - {f}")
    
    return output_dir, output_files

if __name__ == '__main__':
    main()
EOF