#!/usr/bin/env python3
"""
生成最终的section文件 - 基于更细致的分析

分析结果：
- 00_开场: 00:00:00 - 00:03:47 (主播独白)
- 01_98年颜值主播连麦: 00:03:49 - 00:26:44 (22.9分钟)
- 02_对对碰市场评论: 00:26:44 - 00:34:47 (8分钟)
- 03_第二位嘉宾连麦: 00:34:47 - 01:10:00 (约35分钟)
- 04_主播评论: 01:10:00 - 01:17:08 (7分钟)
- 05_第三位嘉宾连麦: 01:17:08 - 01:46:38 (约30分钟)
- 06_主播评论: 01:46:38 - 01:52:30 (6分钟)
- 07_第四位嘉宾连麦: 01:52:30 - 02:22:45 (30分钟)
- ...后续类似结构

注意：由于原始speaker diarization存在问题，同一段连麦中可能出现多个不同的speaker标签。
我们需要基于时间连续性来判断是否为同一次连麦。
"""
import json
import os
from datetime import timedelta

def format_ts(seconds):
    """格式化为 HH:MM:SS.ms"""
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    ms = int((seconds - int(seconds)) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:02d}"

def process_sentences(segments, host_speaker='SPEAKER_02'):
    """处理segments，生成sentences列表"""
    sentences = []
    
    for seg in segments:
        speaker = seg.get('speaker', 'UNKNOWN')
        text = seg.get('text', '').strip()
        
        if not text:
            continue
        
        # 确定speaker_id和speaker_name
        if speaker == host_speaker:
            speaker_id = 'host'
            speaker_name = '曲曲'
        elif speaker == 'UNKNOWN':
            speaker_id = 'unknown'
            speaker_name = '未知'
        else:
            speaker_id = 'guest'
            speaker_name = '嘉宾'
        
        sentences.append({
            'speaker_id': speaker_id,
            'speaker_name': speaker_name,
            'start': seg['start'],
            'end': seg['end'],
            'text': text
        })
    
    return sentences

def create_section_file(section_data, output_dir):
    """创建单个section文件"""
    
    filename = f"{section_data['index']:02d}_{section_data['kind']}_{section_data['persona']}.json"
    filepath = os.path.join(output_dir, filename)
    
    # 构建输出
    output = {
        'meta': {
            'source_file': section_data['source_file'],
            'index': section_data['index'],
            'kind': section_data['kind'],
            'persona': section_data['persona'],
            'title': section_data['title'],
            'start': section_data['start'],
            'end': section_data['end'],
            'start_ts': section_data['start_ts'],
            'end_ts': section_data['end_ts'],
            'raw_segment_count': section_data['raw_segment_count'],
            'speaker_ids': section_data['speaker_ids'],
            'speaker_names': section_data['speaker_names'],
            'sentence_count': len(section_data['sentences']),
            'notes': section_data.get('notes', '')
        },
        'sentences': section_data['sentences']
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    return filepath

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    output_dir = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37_processed'
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    host_speaker = 'SPEAKER_02'
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 基于分析结果定义sections
    # 注意：使用segment索引而不是时间，更精确
    section_defs = [
        (0, 'opening', 0, 59, '00_开场', '主播开场白', '主播介绍直播时间和规则'),
        (1, 'call', 59, 1604, '01_98年颜值主播', '98年颜值主播连麦', '98年颜值主播咨询婚恋问题'),
        (2, 'comment', 1604, 2087, '02_对对碰市场评论', '主播对对碰市场分析', '分析对对碰市场特点'),
        (3, 'call', 2087, 4200, '03_嘉宾2连麦', '第二位嘉宾连麦', '嘉宾咨询情感问题'),
        (4, 'comment', 4200, 4600, '04_主播评论1', '主播评论', '主播对之前连麦的评论'),
        (5, 'call', 4600, 6398, '05_嘉宾3连麦', '第三位嘉宾连麦', '嘉宾咨询婚恋问题'),
        (6, 'comment', 6398, 6800, '06_主播评论2', '主播评论', '主播对之前连麦的评论'),
        (7, 'call', 6800, 8500, '07_嘉宾4连麦', '第四位嘉宾连麦', '嘉宾咨询情感问题'),
        (8, 'comment', 8500, 8956, '08_结尾评论', '主播结尾评论', '主播总结和结束语'),
    ]
    
    created_files = []
    
    for idx, kind, start_idx, end_idx, persona, title, desc in section_defs:
        # 确保索引不越界
        start_idx = max(0, start_idx)
        end_idx = min(end_idx, len(segments))
        
        if start_idx >= end_idx:
            continue
        
        section_segments = segments[start_idx:end_idx]
        
        if not section_segments:
            continue
        
        # 处理sentences
        sentences = process_sentences(section_segments, host_speaker)
        
        # 确定speaker信息
        speakers = set()
        for seg in section_segments:
            speakers.add(seg.get('speaker', 'UNKNOWN'))
        
        speaker_ids = []
        speaker_names = {}
        
        if host_speaker in speakers:
            speaker_ids.append('host')
            speaker_names['host'] = '曲曲'
        
        for spk in speakers:
            if spk not in [host_speaker, 'UNKNOWN']:
                if 'guest' not in speaker_ids:
                    speaker_ids.append('guest')
                    speaker_names['guest'] = '嘉宾'
                break
        
        section_data = {
            'source_file': os.path.basename(input_file),
            'index': idx,
            'kind': kind,
            'persona': persona,
            'title': title,
            'start': section_segments[0]['start'],
            'end': section_segments[-1]['end'],
            'start_ts': format_ts(section_segments[0]['start']),
            'end_ts': format_ts(section_segments[-1]['end']),
            'raw_segment_count': len(section_segments),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentences': sentences,
            'notes': desc
        }
        
        filepath = create_section_file(section_data, output_dir)
        created_files.append(filepath)
        
        duration = (section_segments[-1]['end'] - section_segments[0]['start']) / 60
        print(f"✓ {idx:02d}_{kind}_{persona}: {duration:.1f}分钟, {len(sentences)}句")
    
    print(f"\n共创建 {len(created_files)} 个section文件")
    print(f"输出目录: {output_dir}")

if __name__ == '__main__':
    main()
