#!/usr/bin/env python3
"""
处理直播字幕文件，分割成多个段落并处理每个段落
输出格式符合 formal_output.schema.json
"""
import json
import os
import re
from datetime import timedelta

def format_time(seconds):
    """格式化时间为 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_time_filename(seconds):
    """格式化时间用于文件名 HHMMSS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}{minutes:02d}{secs:02d}"

def identify_speakers(segments, host_speaker='SPEAKER_00'):
    """识别主播和嘉宾"""
    speakers = set()
    for seg in segments:
        spk = seg.get('speaker', 'UNKNOWN')
        if not spk.startswith('UNKNOWN'):
            speakers.add(spk)
    
    # 主播是出现最频繁的说话人（通常是SPEAKER_00）
    if host_speaker in speakers:
        host = host_speaker
    else:
        # 按出现频率选择主播
        speaker_counts = {}
        for seg in segments:
            spk = seg.get('speaker', 'UNKNOWN')
            if not spk.startswith('UNKNOWN'):
                speaker_counts[spk] = speaker_counts.get(spk, 0) + 1
        host = max(speaker_counts.items(), key=lambda x: x[1])[0]
    
    guests = list(speakers - {host})
    
    return host, guests

def process_segment(segments, output_path, section_name):
    """处理一个段落，生成标准格式输出"""
    
    # 识别主播和嘉宾
    host, guests = identify_speakers(segments)
    
    # 构建说话人映射
    speaker_map = {host: 'host'}
    for i, guest in enumerate(guests):
        speaker_map[guest] = f'guest_{i+1}' if len(guests) > 1 else 'guest'
    
    # 构建turns
    turns = []
    for seg in segments:
        spk = seg.get('speaker', 'UNKNOWN')
        if spk in speaker_map:
            text = seg.get('text', '').strip()
            if text:  # 只添加非空文本
                turns.append({
                    'speaker': speaker_map[spk],
                    'text': text,
                    'start': seg.get('start', 0),
                    'end': seg.get('end', 0)
                })
    
    # 构建最终输出
    output = {
        'section_name': section_name,
        'time_range': {
            'start': segments[0]['start'] if segments else 0,
            'end': segments[-1]['end'] if segments else 0
        },
        'speakers': {
            'host': host,
            'guests': guests
        },
        'speaker_mapping': speaker_map,
        'turns': turns
    }
    
    # 保存输出
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    return output

def split_transcript(json_path, output_dir):
    """分割字幕文件为多个段落"""
    
    # 读取JSON文件
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data.get('segments', [])
    
    # 基于分析结果的段落边界
    boundaries = [
        (0, 349, '00_开场'),
        (349, 1012, '01_中外合办本科_连麦'),
        (1012, 5505, '02_超一线女生_连麦'),
        (5505, 14493, '03_后续内容'),
    ]
    
    results = []
    for start_time, end_time, section_name in boundaries:
        section_segments = [
            seg for seg in segments 
            if seg['start'] >= start_time and seg['end'] <= end_time
        ]
        
        if not section_segments:
            continue
        
        output_filename = f"{section_name}_{format_time_filename(start_time)}_{format_time_filename(end_time)}.json"
        output_path = os.path.join(output_dir, output_filename)
        
        result = process_segment(section_segments, output_path, section_name)
        results.append({
            'section': section_name,
            'path': output_path,
            'segments_count': len(section_segments)
        })
        
        print(f"已处理: {section_name} ({len(section_segments)} 段落)")
    
    return results

if __name__ == '__main__':
    json_path = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/32 - 未删减修复版 2024年06月07日  原厂设置专场 #曲曲大女人 #曲曲麦肯锡  #曲曲 #曲曲直播 #美人解忧铺 #金贵的关系.json'
    output_dir = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/32_processed'
    
    os.makedirs(output_dir, exist_ok=True)
    
    results = split_transcript(json_path, output_dir)
    
    print(f"\n处理完成！共处理 {len(results)} 个段落")
