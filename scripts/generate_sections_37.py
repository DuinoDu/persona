#!/usr/bin/env python3
"""
分析直播字幕并生成section文件

基于分析，这场直播的结构如下：
- 开场：0:00 - 3:47 (主播独白)
- 连麦1：3:49 - 26:44 (22.9分钟) - 嘉宾：98年颜值主播
- 评论1：26:44 - 106:38 (主播评论对对碰市场)
- 连麦2：106:38 - 162:48 (56.2分钟) - 包含多位嘉宾
- 评论2：162:48 - 192:11 
- 连麦3：192:11 - 241:51 (49.7分钟) - 包含多位嘉宾
- 结尾：241:51 之后
"""
import json
import os
from datetime import timedelta

def format_time(seconds):
    """格式化时间为 MM:SS"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def format_ts(seconds):
    """格式化为 HH:MM:SS.ms"""
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    ms = int((seconds - int(seconds)) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:02d}"

def identify_sections(segments, host_speaker='SPEAKER_02'):
    """识别各个section"""
    
    sections = []
    
    # 定义时间边界（基于分析结果）
    boundaries = [
        ('opening', 0, 220, '开场白'),
        ('call', 229, 1604, '98年颜值主播连麦'),
        ('comment', 1604, 6398, '对对碰市场分析'),
        ('call', 6398, 9768, '多位嘉宾连麦'),
        ('comment', 9768, 11531, '中场评论'),
        ('call', 11531, 14511, '多位嘉宾连麦'),
        ('comment', 14511, segments[-1]['end'] + 1, '结尾评论'),
    ]
    
    for i, (kind, start_time, end_time, desc) in enumerate(boundaries):
        # 找到对应的segments
        section_segments = []
        for seg in segments:
            if seg['start'] >= start_time and seg['start'] < end_time:
                section_segments.append(seg)
        
        if section_segments:
            # 确定speaker_ids和speaker_names
            speakers = set()
            for seg in section_segments:
                speakers.add(seg.get('speaker', 'UNKNOWN'))
            
            # 主播是host，其他是guest
            speaker_ids = []
            speaker_names = {}
            if host_speaker in speakers:
                speaker_ids.append('host')
                speaker_names['host'] = '主播（曲曲）'
            for spk in speakers:
                if spk != host_speaker and spk != 'UNKNOWN':
                    speaker_ids.append('guest')
                    speaker_names['guest'] = '嘉宾'
                    break
            
            sections.append({
                'index': i,
                'kind': kind,
                'title': desc,
                'start': section_segments[0]['start'],
                'end': section_segments[-1]['end'],
                'start_ts': format_ts(section_segments[0]['start']),
                'end_ts': format_ts(section_segments[-1]['end']),
                'raw_segment_count': len(section_segments),
                'speaker_ids': speaker_ids,
                'speaker_names': speaker_names,
                'segments': section_segments
            })
    
    return sections

def process_sentences(segments, host_speaker='SPEAKER_02'):
    """处理segments，识别句子并确定说话人"""
    sentences = []
    
    for seg in segments:
        speaker = seg.get('speaker', 'UNKNOWN')
        text = seg['text'].strip()
        
        if not text:
            continue
        
        # 确定speaker_id和speaker_name
        if speaker == host_speaker:
            speaker_id = 'host'
            speaker_name = '主播（曲曲）'
        elif speaker == 'UNKNOWN':
            speaker_id = 'unknown'
            speaker_name = '未知'
        else:
            speaker_id = 'guest'
            speaker_name = '嘉宾'
        
        # 简单的句子分割（按逗号、句号等）
        # 但为了保持简洁，我们暂时把整个segment作为一个句子
        sentences.append({
            'speaker_id': speaker_id,
            'speaker_name': speaker_name,
            'start': seg['start'],
            'end': seg['end'],
            'text': text
        })
    
    return sentences

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    output_dir = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37_sections'
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 识别sections
    host_speaker = 'SPEAKER_02'
    sections = identify_sections(segments, host_speaker)
    
    print(f"识别到 {len(sections)} 个section:\n")
    
    for section in sections:
        kind_prefix = '00' if section['kind'] == 'opening' else ('01' if section['kind'] == 'call' else '02')
        print(f"Section {section['index']}: {kind_prefix}_{section['title']}")
        print(f"  时间: {section['start_ts']} - {section['end_ts']}")
        print(f"  时长: {(section['end'] - section['start'])/60:.1f}分钟")
        print(f"  Segments: {section['raw_segment_count']}")
        print(f"  Speakers: {section['speaker_ids']}")
        print()

if __name__ == '__main__':
    main()
