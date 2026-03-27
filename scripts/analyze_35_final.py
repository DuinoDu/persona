#!/usr/bin/env python3
"""
分析字幕文件，划分连麦段落 - 最终版本
使用2分钟窗口分析，然后智能合并
"""
import json
import os

def format_time(seconds):
    """格式化秒数为 HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def analyze_segments(segments):
    """分析段落，识别连麦和主播评论"""
    # 使用2分钟窗口
    window_size = 120
    
    start_time = segments[0]['start']
    end_time = segments[-1]['end']
    num_windows = int((end_time - start_time) // window_size) + 1
    
    windows = []
    current_idx = 0
    
    for win_idx in range(num_windows):
        win_start = start_time + win_idx * window_size
        win_end = win_start + window_size
        
        speakers_count = {}
        
        while current_idx < len(segments) and segments[current_idx]['start'] < win_end:
            if segments[current_idx]['start'] >= win_start:
                speaker = segments[current_idx]['speaker']
                speakers_count[speaker] = speakers_count.get(speaker, 0) + 1
            current_idx += 1
        
        if speakers_count:
            non_unknown = {k: v for k, v in speakers_count.items() if k != 'UNKNOWN'}
            speaker_count = len(non_unknown)
            
            if speaker_count >= 2:
                win_type = "call"
            else:
                win_type = "host"
            
            windows.append({
                'start': win_start,
                'end': win_end,
                'type': win_type,
                'speakers': list(non_unknown.keys()),
                'speaker_counts': dict(non_unknown)
            })
    
    return windows

def merge_windows(windows):
    """智能合并窗口"""
    if not windows:
        return []
    
    merged = []
    current = windows[0].copy()
    
    for w in windows[1:]:
        # 判断是否合并
        should_merge = False
        
        if w['type'] == current['type']:
            # 同类型，直接合并
            should_merge = True
        elif current['type'] == 'call' and w['type'] == 'host':
            # 连麦中出现主播，如果很短（<4分钟），认为是连麦内的主播说话
            host_duration = w['end'] - w['start']
            if host_duration < 240:  # 4分钟
                should_merge = True
        elif current['type'] == 'host' and w['type'] == 'call':
            # 主播评论中出现连麦，如果很短（<2分钟），合并
            call_duration = w['end'] - w['start']
            if call_duration < 120:  # 2分钟
                should_merge = True
        
        if should_merge:
            # 合并
            current['end'] = w['end']
            current['speakers'] = list(set(current['speakers']) | set(w['speakers']))
            # 更新说话人计数
            for spk, cnt in w['speaker_counts'].items():
                current['speaker_counts'][spk] = current['speaker_counts'].get(spk, 0) + cnt
        else:
            # 不合并，保存当前，开始新的
            merged.append(current)
            current = w.copy()
    
    merged.append(current)
    return merged

def print_results(merged):
    """打印分析结果"""
    print(f"\n分析结果: 共 {len(merged)} 个段落\n")
    print("=" * 100)
    
    call_count = 0
    host_count = 0
    
    for i, m in enumerate(merged):
        start_str = format_time(m['start'])
        end_str = format_time(m['end'])
        
        duration_min = (m['end'] - m['start']) / 60
        
        if m['type'] == 'call':
            call_count += 1
            type_str = f"【连麦{call_count}】"
        else:
            host_count += 1
            type_str = f"【主播评论{host_count}】"
        
        # 找出主要说话人（按说话量排序）
        sorted_speakers = sorted(m['speaker_counts'].items(), key=lambda x: -x[1])
        speakers_str = ", ".join([f"{s}({c})" for s, c in sorted_speakers[:3]])
        
        print(f"\n[{i:02d}] {type_str}")
        print(f"     时间: {start_str} - {end_str}")
        print(f"     时长: {duration_min:.1f}分钟")
        print(f"     说话人: {speakers_str}")

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
    
    windows = analyze_segments(segments)
    merged = merge_windows(windows)
    
    print_results(merged)
    
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
    
    with open(f"{output_dir}/analysis_detailed.json", 'w', encoding='utf-8') as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n分析结果已保存到: {output_dir}/analysis_detailed.json")
    
    # 统计
    call_count = sum(1 for m in merged if m['type'] == 'call')
    host_count = sum(1 for m in merged if m['type'] == 'host')
    print(f"\n总计: {call_count}次连麦, {host_count}段主播评论")

if __name__ == "__main__":
    main()
