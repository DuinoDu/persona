#!/usr/bin/env python3
"""
处理单个段落，识别说话人、划分句子并输出符合schema的JSON
"""
import json
import sys
import os

def seconds_to_ts(seconds):
    """将秒数转换为 HH:MM:SS.ss 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"

def merge_segments_into_sentences(segments, speaker_mapping):
    """
    将连续的同说话人片段合并为句子
    """
    if not segments:
        return []
    
    sentences = []
    current_speaker = segments[0]['speaker']
    current_start = segments[0]['start']
    current_end = segments[0]['end']
    current_text = segments[0]['text']
    
    for seg in segments[1:]:
        # 如果说话人相同且间隔小于2秒，合并
        if seg['speaker'] == current_speaker and seg['start'] - current_end < 2.0:
            current_end = seg['end']
            current_text += seg['text']
        else:
            # 保存当前句子
            speaker_id = speaker_mapping.get(current_speaker, 'unknown')
            sentences.append({
                "speaker_id": speaker_id,
                "speaker_name": "主播" if speaker_id == "host" else "嘉宾",
                "start": current_start,
                "end": current_end,
                "text": current_text.strip()
            })
            # 开始新句子
            current_speaker = seg['speaker']
            current_start = seg['start']
            current_end = seg['end']
            current_text = seg['text']
    
    # 保存最后一个句子
    speaker_id = speaker_mapping.get(current_speaker, 'unknown')
    sentences.append({
        "speaker_id": speaker_id,
        "speaker_name": "主播" if speaker_id == "host" else "嘉宾",
        "start": current_start,
        "end": current_end,
        "text": current_text.strip()
    })
    
    return sentences

def process_section(input_file, output_file, section_info):
    """处理单个段落"""
    
    # 读取原始数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_segments = data['segments']
    
    # 提取该时间段的segments
    start_time = section_info['start']
    end_time = section_info['end']
    
    section_segments = [
        s for s in all_segments 
        if s['start'] >= start_time and s['end'] <= end_time
        or (s['start'] < end_time and s['end'] > start_time)
    ]
    
    # 按时间排序
    section_segments.sort(key=lambda x: x['start'])
    
    # 确定说话人映射
    section_type = section_info['type']
    guest_speaker = section_info.get('guest_speaker')
    
    # 分析该段中的说话人
    speakers_in_section = set(s['speaker'] for s in section_segments)
    
    # 创建说话人映射
    speaker_mapping = {}
    
    # 主播识别逻辑
    # SPEAKER_01通常是主播（曲曲）
    if 'SPEAKER_01' in speakers_in_section:
        speaker_mapping['SPEAKER_01'] = 'host'
    
    # 如果是连麦类型，确定嘉宾
    if section_type == 'call' and guest_speaker:
        if guest_speaker in speakers_in_section:
            speaker_mapping[guest_speaker] = 'guest'
    
    # 其他说话人标记为unknown
    for spk in speakers_in_section:
        if spk not in speaker_mapping:
            speaker_mapping[spk] = 'unknown'
    
    # 合并为句子
    sentences = merge_segments_into_sentences(section_segments, speaker_mapping)
    
    # 创建输出结构
    output = {
        "meta": {
            "source_file": os.path.basename(input_file),
            "index": section_info['index'],
            "kind": section_type,
            "persona": section_info['persona'],
            "title": section_info['name'],
            "start": start_time,
            "end": end_time,
            "start_ts": seconds_to_ts(start_time),
            "end_ts": seconds_to_ts(end_time),
            "raw_segment_count": len(section_segments),
            "speaker_ids": list(set(s['speaker_id'] for s in sentences)),
            "speaker_names": {
                "host": "曲曲" if 'host' in [s['speaker_id'] for s in sentences] else "",
                "guest": "嘉宾" if 'guest' in [s['speaker_id'] for s in sentences] else ""
            },
            "sentence_count": len(sentences),
            "notes": section_info['description']
        },
        "sentences": sentences
    }
    
    # 保存输出
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"处理完成: {section_info['name']}")
    print(f"  - 原始片段数: {len(section_segments)}")
    print(f"  - 合并后句子数: {len(sentences)}")
    print(f"  - 说话人: {set(s['speaker'] for s in section_segments)}")
    print(f"  - 输出文件: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: process_section.py <input_file> <output_file> <section_info_json>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    section_info = json.loads(sys.argv[3])
    
    process_section(input_file, output_file, section_info)
