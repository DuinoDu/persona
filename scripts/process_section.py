#!/usr/bin/env python3
"""
处理直播字幕文件的单个段落
输入：原始字幕文件路径、段落索引、开始时间、结束时间、段落类型、标题
输出：符合schema的JSON文件
"""
import json
import sys
from datetime import timedelta

def format_timestamp(seconds):
    """将秒数转换为 HH:MM:SS.ff 格式"""
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    frac = int((seconds % 1) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{frac:02d}"

def merge_short_segments(segments, min_duration=0.5):
    """合并过短的片段"""
    if not segments:
        return []
    
    merged = []
    current = dict(segments[0])
    
    for seg in segments[1:]:
        if seg['end'] - seg['start'] < min_duration and current['speaker'] == seg['speaker']:
            # 合并到当前片段
            current['end'] = seg['end']
            current['text'] = current['text'] + seg['text'] if current['text'] and seg['text'] else current['text'] or seg['text']
        elif seg['start'] - current['end'] < 0.3 and current['speaker'] == seg['speaker']:
            # 几乎连续的同speaker片段，合并
            current['end'] = seg['end']
            current['text'] = current['text'] + seg['text'] if current['text'] and seg['text'] else current['text'] or seg['text']
        else:
            merged.append(current)
            current = dict(seg)
    
    merged.append(current)
    return merged

def split_into_sentences(segment):
    """将长文本分割成句子"""
    text = segment['text'].strip()
    if not text:
        return []
    
    # 简单的句子分割（按标点符号）
    import re
    # 匹配中文标点或英文句末标点
    sentence_end = r'([。！？；.!?;])'
    parts = re.split(sentence_end, text)
    
    sentences = []
    current = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:  # 文本部分
            current = part
        else:  # 标点部分
            current += part
            if current.strip():
                sentences.append(current.strip())
            current = ""
    
    if current.strip():
        sentences.append(current.strip())
    
    # 如果没有分割成功，返回整个文本
    if not sentences:
        sentences = [text]
    
    return sentences

def process_section(input_file, section_idx, start_time, end_time, kind, persona, title):
    """处理单个段落"""
    
    # 读取原始字幕文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取该时间段的片段
    segments = []
    for seg in data['segments']:
        if seg['start'] >= start_time and seg['end'] <= end_time:
            segments.append(seg)
        elif seg['start'] < end_time and seg['end'] > start_time:
            # 部分重叠
            clipped_seg = dict(seg)
            clipped_seg['start'] = max(seg['start'], start_time)
            clipped_seg['end'] = min(seg['end'], end_time)
            segments.append(clipped_seg)
    
    if not segments:
        print(f"Warning: No segments found for section {section_idx}")
        return None
    
    # 合并短片段
    segments = merge_short_segments(segments)
    
    # 识别说话人
    speaker_mapping = {}
    all_speakers = list(set(seg['speaker'] for seg in segments if seg.get('speaker')))
    
    # 主主播应该是SPEAKER_00或出现最多的speaker
    speaker_counts = {}
    for seg in segments:
        spk = seg.get('speaker', 'UNKNOWN')
        speaker_counts[spk] = speaker_counts.get(spk, 0) + (seg['end'] - seg['start'])
    
    if speaker_counts:
        main_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
        speaker_mapping[main_speaker] = ('host', '曲曲')
        
        # 其他标记为guest
        guest_idx = 1
        for spk in all_speakers:
            if spk != main_speaker and spk not in speaker_mapping:
                speaker_mapping[spk] = (f'guest', f'嘉宾{guest_idx}')
                guest_idx += 1
    
    # 处理句子
    sentences = []
    for seg in segments:
        seg_sentences = split_into_sentences(seg)
        
        # 为每个句子分配时间戳
        seg_duration = seg['end'] - seg['start']
        if seg_sentences:
            sentence_duration = seg_duration / len(seg_sentences)
        else:
            sentence_duration = seg_duration
        
        for i, sent_text in enumerate(seg_sentences):
            if not sent_text.strip():
                continue
            
            sent_start = seg['start'] + i * sentence_duration
            sent_end = sent_start + sentence_duration
            
            speaker = seg.get('speaker', 'UNKNOWN')
            speaker_id, speaker_name = speaker_mapping.get(speaker, ('unknown', '未知'))
            
            sentences.append({
                'speaker_id': speaker_id,
                'speaker_name': speaker_name,
                'start': round(sent_start, 2),
                'end': round(sent_end, 2),
                'text': sent_text
            })
    
    # 构建输出
    output = {
        'meta': {
            'source_file': '76 - 曲曲現場直播 2024年11月8日 ｜ 曲曲麥肯錫.json',
            'index': section_idx,
            'kind': kind,
            'persona': persona,
            'title': title,
            'start': start_time,
            'end': end_time,
            'start_ts': format_timestamp(start_time),
            'end_ts': format_timestamp(end_time),
            'raw_segment_count': len(segments),
            'speaker_ids': ['host'] if kind == 'comment' else ['host', 'guest'],
            'speaker_names': {'host': '曲曲'},
            'sentence_count': len(sentences),
            'notes': f'Auto-generated section {section_idx}'
        },
        'sentences': sentences
    }
    
    if kind == 'call':
        output['meta']['speaker_names']['guest'] = persona
    
    return output

if __name__ == '__main__':
    if len(sys.argv) < 8:
        print("Usage: process_section.py <input_file> <section_idx> <start_time> <end_time> <kind> <persona> <title>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    section_idx = int(sys.argv[2])
    start_time = float(sys.argv[3])
    end_time = float(sys.argv[4])
    kind = sys.argv[5]
    persona = sys.argv[6]
    title = sys.argv[7]
    
    result = process_section(input_file, section_idx, start_time, end_time, kind, persona, title)
    
    if result:
        output_file = f"/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/76_processed/{section_idx:02d}_{kind}_{persona}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved: {output_file}")
    else:
        print("No result generated")