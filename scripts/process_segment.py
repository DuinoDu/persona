#!/usr/bin/env python3
"""
处理字幕段落文件：
1. 识别说话人（主播/嘉宾）
2. 合并同一说话人的连续segment
3. 分句并保留时间戳
4. 输出符合schema.json格式的结果
"""

import json
import sys
import os
import re

# 语气词过滤
FILLER_WORDS = {'嗯', '啊', '呃', '哦', '哎', '哟', '哈', '呵', '嘿', '咳', '哇'}

def is_filler(text):
    """检查文本是否只包含语气词或空字符"""
    if not text or not text.strip():
        return True
    # 去除语气词后是否为空
    cleaned = text
    for filler in FILLER_WORDS:
        cleaned = cleaned.replace(filler, '')
    return not cleaned.strip()

def merge_same_speaker_segments(segments):
    """合并同一说话人的连续segments"""
    if not segments:
        return []
    
    merged = []
    current = {
        'speaker': segments[0]['speaker'],
        'start': segments[0]['start'],
        'end': segments[0]['end'],
        'text': segments[0]['text']
    }
    
    for seg in segments[1:]:
        if seg['speaker'] == current['speaker']:
            # 同一说话人，合并
            current['end'] = seg['end']
            current['text'] += seg['text']
        else:
            # 不同说话人，保存当前并开始新的
            merged.append(current)
            current = {
                'speaker': seg['speaker'],
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text']
            }
    
    merged.append(current)
    return merged

def split_into_sentences(text, start_time, end_time):
    """
    将文本分句，并按比例分配时间戳
    """
    if not text or not text.strip():
        return []
    
    # 使用常见的句子结束符分句
    # 保留分隔符
    parts = re.split(r'([。！？，；：\n])', text)
    
    sentences = []
    current = ''
    
    for part in parts:
        if not part:
            continue
        if part in '。！？，；：\n':
            current += part
            # 遇到结束符，保存句子
            if current.strip():
                sentences.append(current.strip())
            current = ''
        else:
            current += part
    
    # 处理剩余的内容
    if current.strip():
        sentences.append(current.strip())
    
    # 如果分句失败，返回整段文本
    if not sentences:
        sentences = [text.strip()]
    
    # 按比例分配时间戳
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return [{'text': text, 'start': start_time, 'end': end_time}]
    
    result = []
    current_time = start_time
    duration = end_time - start_time
    
    for i, sentence in enumerate(sentences):
        char_ratio = len(sentence) / total_chars
        sentence_duration = duration * char_ratio
        
        # 最后一句延伸到结束时间
        if i == len(sentences) - 1:
            sentence_end = end_time
        else:
            sentence_end = current_time + sentence_duration
        
        result.append({
            'text': sentence,
            'start': round(current_time, 2),
            'end': round(sentence_end, 2)
        })
        
        current_time = sentence_end
    
    return result

def process_file(input_file, output_file):
    """处理单个文件"""
    
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data.get('segments', [])
    host = data.get('host', 'SPEAKER_01')
    guest = data.get('guest')
    seg_type = data.get('segment_type', 'unknown')
    
    if not segments:
        print(f"Warning: No segments in {input_file}")
        return
    
    # 步骤1：合并同一说话人的连续segments
    merged = merge_same_speaker_segments(segments)
    
    # 步骤2：过滤语气词/空文本，分句
    sentences = []
    
    for item in merged:
        text = item['text']
        
        # 跳过纯语气词
        if is_filler(text):
            continue
        
        # 分句并分配时间戳
        item_sentences = split_into_sentences(
            text, 
            item['start'], 
            item['end']
        )
        
        for sent in item_sentences:
            # 确定说话人角色
            speaker_id = item['speaker']
            if speaker_id == host:
                role = 'host'
            elif speaker_id == guest:
                role = 'guest'
            else:
                role = 'other'
            
            sentences.append({
                'text': sent['text'],
                'start': sent['start'],
                'end': sent['end'],
                'speaker': speaker_id,
                'role': role
            })
    
    # 构建输出
    output = {
        'segment_index': data.get('segment_index'),
        'segment_type': seg_type,
        'start_time': data.get('start_time'),
        'end_time': data.get('end_time'),
        'duration': data.get('duration'),
        'host': host,
        'guest': guest,
        'sentences': sentences
    }
    
    # 保存输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"Processed: {os.path.basename(input_file)} -> {os.path.basename(output_file)}")
    print(f"  Input segments: {len(segments)} -> Output sentences: {len(sentences)}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python process_segment.py <input_file> <output_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    process_file(input_file, output_file)

if __name__ == '__main__':
    main()
