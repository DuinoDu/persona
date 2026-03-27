#!/usr/bin/env python3
"""
分析字幕文件，划分连麦段落
"""
import json
import os

def analyze_segments(segments):
    """分析段落，识别连麦和主播评论"""
    # 按5分钟块分析
    block_size = 300  # 5分钟

    start_time = segments[0]['start']
    end_time = segments[-1]['end']

    blocks = []
    current_idx = 0
    num_blocks = int((end_time - start_time) // block_size) + 1

    for block_idx in range(num_blocks):
        block_start = start_time + block_idx * block_size
        block_end = block_start + block_size

        speakers_count = {}
        samples = []

        while current_idx < len(segments) and segments[current_idx]['start'] < block_end:
            if segments[current_idx]['start'] >= block_start:
                speaker = segments[current_idx]['speaker']
                speakers_count[speaker] = speakers_count.get(speaker, 0) + 1
                if len(samples) < 2:
                    samples.append(segments[current_idx]['text'][:40])
            current_idx += 1

        if speakers_count:
            # 判断类型
            non_unknown = {k: v for k, v in speakers_count.items() if k != 'UNKNOWN'}
            speaker_count = len(non_unknown)

            if speaker_count >= 2:
                call_type = "call"
            else:
                call_type = "host"

            blocks.append({
                'idx': block_idx,
                'start': block_start,
                'end': block_end,
                'speakers': speakers_count,
                'type': call_type,
                'samples': samples
            })

    return blocks

def merge_segments(blocks):
    """合并连续的同类型段落"""
    if not blocks:
        return []

    merged = []
    current = {
        'start': blocks[0]['start'],
        'end': blocks[0]['end'],
        'type': blocks[0]['type'],
        'speakers': dict(blocks[0]['speakers']),
        'samples': list(blocks[0]['samples'])
    }

    for b in blocks[1:]:
        if b['type'] == current['type'] and len(current['samples']) < 5:
            # 合并
            current['end'] = b['end']
            for spk, cnt in b['speakers'].items():
                current['speakers'][spk] = current['speakers'].get(spk, 0) + cnt
            current['samples'].extend(b['samples'])
        else:
            merged.append(current)
            current = {
                'start': b['start'],
                'end': b['end'],
                'type': b['type'],
                'speakers': dict(b['speakers']),
                'samples': list(b['samples'])
            }

    merged.append(current)
    return merged

def print_analysis(merged):
    """打印分析结果"""
    print(f"\n共识别出 {len(merged)} 个段落:\n")
    print("=" * 100)

    for i, m in enumerate(merged):
        start_h = int(m['start'] // 3600)
        start_m = int((m['start'] % 3600) // 60)
        start_s = int(m['start'] % 60)
        end_h = int(m['end'] // 3600)
        end_m = int((m['end'] % 3600) // 60)
        end_s = int(m['end'] % 60)

        duration_min = (m['end'] - m['start']) / 60

        type_str = "【连麦】" if m['type'] == 'call' else "【主播】"

        # 主要说话人
        non_unknown = {k: v for k, v in m['speakers'].items() if k != 'UNKNOWN'}
        main_speakers = sorted(non_unknown.items(), key=lambda x: -x[1])[:3]
        speaker_str = ", ".join([f"{s}({c})" for s, c in main_speakers])

        samples_str = " | ".join(m['samples'][:3])

        print(f"\n[{i:02d}] {type_str}")
        print(f"     时间: {start_h:02d}:{start_m:02d}:{start_s:02d} - {end_h:02d}:{end_m:02d}:{end_s:02d}")
        print(f"     时长: {duration_min:.1f}分钟")
        print(f"     说话人: {speaker_str}")
        print(f"     示例: {samples_str[:100]}...")

def main():
    input_file = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/35 - 曲曲直播未删减修复版 2024年06月20日 高清分章节  #曲曲麦肯锡.json"

    print(f"正在分析: {input_file}")

    with open(input_file, 'r') as f:
        data = json.load(f)

    segments = data['segments']

    print(f"\n字幕段数: {len(segments)}")
    print(f"开始时间: {segments[0]['start']:.2f}s")
    print(f"结束时间: {segments[-1]['end']:.2f}s")
    print(f"总时长: {(segments[-1]['end'] - segments[0]['start'])/3600:.2f}小时")

    blocks = analyze_segments(segments)
    merged = merge_segments(blocks)

    print_analysis(merged)

    # 保存分析结果
    output_dir = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/35_processed"
    os.makedirs(output_dir, exist_ok=True)

    analysis_result = {
        "total_segments": len(segments),
        "start_time": segments[0]['start'],
        "end_time": segments[-1]['end'],
        "duration_hours": (segments[-1]['end'] - segments[0]['start']) / 3600,
        "segments_count": len(merged),
        "segments": merged
    }

    with open(f"{output_dir}/analysis.json", 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)

    print(f"\n分析结果已保存到: {output_dir}/analysis.json")

if __name__ == "__main__":
    main()
