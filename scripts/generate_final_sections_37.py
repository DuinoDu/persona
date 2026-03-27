#!/usr/bin/env python3
"""
生成最终的section文件

根据分析，这场直播结构如下：
- 00_开场: 00:00:06.92 - 00:03:38.75 (主播独白)
- 01_98年颜值主播连麦: 00:03:49.15 - 00:26:44.35 (嘉宾: 98年颜值主播)
- 02_对对碰市场分析: 00:26:45.79 - 01:46:37.31 (主播评论，中间可能穿插短互动)
- 03_多位嘉宾连麦: 01:46:38.38 - 02:42:48.97 (多位嘉宾)
- 04_中场评论: 02:42:48.97 - 03:12:08.88 (主播评论)
- 05_多位嘉宾连麦: 03:12:11.06 - 04:01:50.62 (多位嘉宾)
- 06_结尾评论: 04:01:51.04 - 04:09:46.60 (主播评论)
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

def create_section_file(section_data, output_dir, schema):
    """创建单个section文件"""
    
    filename = f"{section_data['index']:02d}_{section_data['kind']}_{section_data['persona']}.json"
    filepath = os.path.join(output_dir, filename)
    
    # 构建符合schema的输出
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
    output_dir = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37_sections'
    schema_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/formal_output.schema.json'
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载schema（用于验证）
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    host_speaker = 'SPEAKER_02'
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 定义sections（基于之前的分析）
    section_defs = [
        (0, 'opening', 0, 229, '00_开场', '主播开场白'),
        (1, 'call', 229, 1604, '01_98年颜值主播', '98年颜值主播连麦'),
        (2, 'comment', 1604, 6398, '02_对对碰市场分析', '主播对对碰市场分析'),
        (3, 'call', 6398, 9768, '03_多位嘉宾连麦', '多位嘉宾连麦'),
        (4, 'comment', 9768, 11531, '04_中场评论', '主播中场评论'),
        (5, 'call', 11531, 14511, '05_多位嘉宾连麦', '多位嘉宾连麦'),
        (6, 'comment', 14511, len(segments), '06_结尾评论', '主播结尾评论'),
    ]
    
    # 修正最后一个section的结束索引
    section_defs = [(idx, kind, start, min(end, len(segments)), persona, title) for idx, kind, start, end, persona, title in section_defs]
    
    created_files = []
    
    for idx, kind, start_idx, end_idx, persona, title in section_defs:
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
        
        # 构建section数据
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
            'notes': f'时长: {(section_segments[-1]["end"] - section_segments[0]["start"])/60:.1f}分钟'
        }
        
        filepath = create_section_file(section_data, output_dir, schema)
        created_files.append(filepath)
        
        print(f"✓ 创建: {os.path.basename(filepath)}")
        print(f"  类型: {kind}, 时长: {(section_segments[-1]['end'] - section_segments[0]['start'])/60:.1f}分钟, 句子数: {len(sentences)}")
    
    print(f"\n共创建 {len(created_files)} 个section文件")
    print(f"输出目录: {output_dir}")

if __name__ == '__main__':
    main()
