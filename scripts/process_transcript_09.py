#!/usr/bin/env python3
"""
处理字幕文件，划分段落，识别说话人，输出符合schema格式的文件
"""

import json
import sys
import os
import re
from datetime import timedelta
from pathlib import Path

def format_timestamp(seconds):
    """将秒数转换为 HH:MM:SS.ss 格式"""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = td.total_seconds() % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"

def merge_same_speaker_segments(segments):
    """合并同一speaker的连续segments"""
    if not segments:
        return []
    
    merged = []
    for seg in segments:
        if merged and merged[-1]['speaker'] == seg['speaker']:
            merged[-1]['end'] = seg['end']
            merged[-1]['text'] += seg['text']
        else:
            merged.append({
                'start': seg['start'],
                'end': seg['end'],
                'speaker': seg['speaker'],
                'text': seg['text']
            })
    return merged

def split_into_sentences(text):
    """将文本分割成句子"""
    # 中文句子结束符
    sentence_endings = r'[。！？\.\!\?]'
    
    sentences = []
    current = ""
    for char in text:
        current += char
        if re.match(sentence_endings, char):
            if current.strip():
                sentences.append(current.strip())
            current = ""
    
    if current.strip():
        sentences.append(current.strip())
    
    if not sentences:
        sentences = [text] if text.strip() else []
    
    return sentences

def detect_calls(segments, min_duration=60):
    """检测连麦段落"""
    merged = merge_same_speaker_segments(segments)
    
    calls = []
    i = 0
    while i < len(merged):
        seg = merged[i]
        
        if seg['speaker'] != 'SPEAKER_00' and seg['speaker'] != 'UNKNOWN':
            guest = seg['speaker']
            call_start = seg['start']
            call_segments = [seg]
            last_guest_end = seg['end']
            
            j = i + 1
            while j < len(merged):
                next_seg = merged[j]
                
                if next_seg['speaker'] == guest:
                    call_segments.append(next_seg)
                    last_guest_end = next_seg['end']
                    j += 1
                elif next_seg['speaker'] == 'SPEAKER_00':
                    # 检查主播持续时间
                    host_duration = next_seg['end'] - next_seg['start']
                    k = j + 1
                    continuous_host = host_duration
                    while k < len(merged) and merged[k]['speaker'] == 'SPEAKER_00':
                        continuous_host += merged[k]['end'] - merged[k]['start']
                        k += 1
                    
                    if continuous_host > 30:
                        break
                    j += 1
                else:
                    break
            
            if call_segments:
                total_duration = sum(s['end'] - s['start'] for s in call_segments)
                if total_duration >= min_duration:
                    calls.append({
                        'guest': guest,
                        'start': call_start,
                        'end': last_guest_end,
                        'duration': total_duration,
                        'segments': call_segments
                    })
            
            i = j
            continue
        
        i += 1
    
    return calls

def create_section(kind, index, start, end, segments, source_file, persona=""):
    """创建一个section对象"""
    
    # 确定speaker信息
    speakers = set(seg['speaker'] for seg in segments)
    speaker_ids = []
    speaker_names = {}
    
    if kind == "call":
        speaker_ids = ["host", "guest"]
        speaker_names = {"host": "主播", "guest": "嘉宾"}
    else:
        speaker_ids = ["host"]
        speaker_names = {"host": "主播"}
    
    # 处理sentences
    sentences = []
    for seg in segments:
        speaker_id = "host" if seg['speaker'] == 'SPEAKER_00' else "guest"
        speaker_name = speaker_names.get(speaker_id, "未知")
        
        # 分割句子
        text = seg['text'].strip()
        if text:
            # 简单处理：将整个segment作为一个句子
            sentences.append({
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "start": seg['start'],
                "end": seg['end'],
                "text": text
            })
    
    # 创建title
    if kind == "opening":
        title = "开场"
    elif kind == "call":
        title = f"嘉宾连麦 - {persona}"
    elif kind == "comment":
        title = "主播评论"
    else:
        title = f"段落{index}"
    
    return {
        "meta": {
            "source_file": source_file,
            "index": index,
            "kind": kind,
            "persona": persona,
            "title": title,
            "start": start,
            "end": end,
            "start_ts": format_timestamp(start),
            "end_ts": format_timestamp(end),
            "raw_segment_count": len(segments),
            "speaker_ids": speaker_ids,
            "speaker_names": speaker_names,
            "sentence_count": len(sentences),
            "notes": ""
        },
        "sentences": sentences
    }

def process_transcript(input_file, output_dir):
    """处理字幕文件的主函数"""
    
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data.get('segments', [])
    if not segments:
        print("No segments found in input file")
        return
    
    # 检测连麦
    calls = detect_calls(segments, min_duration=60)
    print(f"Detected {len(calls)} calls")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取文件名（不含扩展名）
    base_name = os.path.basename(input_file)
    base_name = os.path.splitext(base_name)[0]
    
    # 创建段落
    sections = []
    current_time = segments[0]['start']
    section_index = 0
    
    # 第一个段落是开场
    if calls:
        first_call_start = calls[0]['start']
        # 开场段落：从开始到第一个连麦开始
        opening_segments = [s for s in segments if s['start'] >= current_time and s['end'] <= first_call_start]
        if opening_segments:
            section = create_section(
                kind="opening",
                index=section_index,
                start=opening_segments[0]['start'],
                end=opening_segments[-1]['end'],
                segments=opening_segments,
                source_file=base_name
            )
            sections.append(section)
            section_index += 1
            current_time = first_call_start
    
    # 处理连麦和评论
    for i, call in enumerate(calls):
        # 如果前面有间隔，创建评论段落
        if current_time < call['start']:
            comment_segments = [s for s in segments if s['start'] >= current_time and s['end'] <= call['start']]
            if comment_segments:
                section = create_section(
                    kind="comment",
                    index=section_index,
                    start=comment_segments[0]['start'],
                    end=comment_segments[-1]['end'],
                    segments=comment_segments,
                    source_file=base_name
                )
                sections.append(section)
                section_index += 1
        
        # 创建连麦段落
        call_segments = call['segments']
        if call_segments:
            section = create_section(
                kind="call",
                index=section_index,
                start=call['start'],
                end=call['end'],
                segments=call_segments,
                source_file=base_name,
                persona=call['guest']
            )
            sections.append(section)
            section_index += 1
        
        current_time = call['end']
    
    # 处理最后一段（如果有的话）
    if current_time < segments[-1]['end']:
        final_segments = [s for s in segments if s['start'] >= current_time]
        if final_segments:
            section = create_section(
                kind="comment",
                index=section_index,
                start=final_segments[0]['start'],
                end=final_segments[-1]['end'],
                segments=final_segments,
                source_file=base_name
            )
            sections.append(section)
    
    # 保存每个section为单独的文件
    for section in sections:
        kind = section['meta']['kind']
        index = section['meta']['index']
        persona = section['meta'].get('persona', '')
        
        # 创建文件名
        if kind == 'opening':
            filename = f"{index:02d}_opening.json"
        elif kind == 'call':
            filename = f"{index:02d}_call_{persona}.json"
        elif kind == 'comment':
            filename = f"{index:02d}_comment.json"
        else:
            filename = f"{index:02d}_{kind}.json"
        
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(section, f, ensure_ascii=False, indent=2)
        
        print(f"Saved: {filename}")
    
    print(f"\nTotal sections: {len(sections)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python process_transcript.py <input_file> <output_dir>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    process_transcript(input_file, output_dir)
