#!/usr/bin/env python3
"""
将 processed 文件转换为符合 formal_output.schema.json 的格式
"""

import json
import os
import sys

def format_time_schema(seconds):
    """格式化为 HH:MM:SS.XX (两位小数)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:02d}"

def convert_to_schema(input_file, output_file=None):
    """转换文件为schema格式"""

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    meta = data.get('metadata', {})
    sentences = data.get('sentences', [])

    if not sentences:
        print(f"警告: {input_file} 没有句子数据")
        return None

    seg_type = meta.get('segment_type', '评论')
    segment_index = meta.get('segment_index', 0)
    start_time = meta.get('start_time', 0)
    end_time = meta.get('end_time', 0)
    speaker_mapping = meta.get('speaker_mapping', {})

    # 确定kind
    kind_map = {'开场白': 'opening', '连麦': 'call', '评论': 'comment'}
    kind = kind_map.get(seg_type, 'comment')

    # 确定序号和persona
    if seg_type == '开场白':
        persona = '开场白'
        title = '开场白'
    elif seg_type == '连麦':
        call_num = (segment_index + 1) // 2
        persona = f'第{call_num}位嘉宾连麦'
        title = f'连麦{call_num}'
    else:  # 评论
        comment_num = segment_index // 2
        persona = f'第{comment_num}段评论'
        title = f'评论{comment_num}'

    # 确定speaker_ids和speaker_names
    if kind == 'call':
        speaker_ids = ['host', 'guest']
        speaker_names = {'host': '主播', 'guest': '嘉宾'}
    else:
        speaker_ids = ['host']
        speaker_names = {'host': '主播'}

    # 转换sentences
    transformed_sentences = []
    for sent in sentences:
        speaker = sent.get('speaker', '')

        if speaker == 'HOST':
            speaker_id = 'host'
            speaker_name = '主播'
        elif speaker.startswith('GUEST_'):
            speaker_id = 'guest'
            speaker_name = '嘉宾'
        else:
            speaker_id = 'host'
            speaker_name = '主播'

        transformed_sentences.append({
            'speaker_id': speaker_id,
            'speaker_name': speaker_name,
            'start': sent.get('start', 0),
            'end': sent.get('end', 0),
            'text': sent.get('text', '')
        })

    # 构建输出
    output = {
        'meta': {
            'source_file': meta.get('source_file', ''),
            'index': segment_index,
            'kind': kind,
            'persona': persona,
            'title': title,
            'start': start_time,
            'end': end_time,
            'start_ts': format_time_schema(start_time),
            'end_ts': format_time_schema(end_time),
            'raw_segment_count': meta.get('total_segments', 0),
            'speaker_ids': speaker_ids,
            'speaker_names': speaker_names,
            'sentence_count': len(transformed_sentences),
            'notes': ''
        },
        'sentences': transformed_sentences
    }

    # 保存输出
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_formal.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_to_formal.py <input_file> [output_file]")
        print("Example:")
        print("  python convert_to_formal.py 01_开场白_processed.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    result = convert_to_formal_schema(input_file, output_file)

    if result:
        meta = result['meta']
        print(f"转换完成!")
        print(f"  文件: {output_file or '自动命名'}")
        print(f"  类型: {meta['kind']}")
        print(f"  标题: {meta['title']}")
        print(f"  句子数: {meta['sentence_count']}")

if __name__ == '__main__':
    main()
