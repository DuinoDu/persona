#!/usr/bin/env python3
"""
重新分析直播字幕，基于内容识别真正的连麦段落

策略：
1. 主播通常是说话最多的人，会说"宝子们"、"欢迎大家"等标志性语言
2. 连麦开始：主播说"你好"、"哈喽"等，然后嘉宾开始自我介绍
3. 连麦结束：嘉宾说"拜拜"、"谢谢"等，然后主播开始独白评论
4. 同一次连麦中，主播和嘉宾的segment应该交替出现

由于原始speaker diarization有问题，我们需要基于时间连续性重新分组
"""
import json
import os
from collections import defaultdict

def find_host(segments):
    """找出主播：说话次数最多且包含标志性词汇的人"""
    speaker_stats = defaultdict(lambda: {'count': 0, 'host_markers': 0, 'total_time': 0})
    
    host_markers = ['宝子们', '欢迎大家', '我们直接开始连麦', '哈喽', '每人解忧铺']
    
    for seg in segments:
        spk = seg.get('speaker', 'UNKNOWN')
        text = seg.get('text', '')
        duration = seg['end'] - seg['start']
        
        speaker_stats[spk]['count'] += 1
        speaker_stats[spk]['total_time'] += duration
        
        for marker in host_markers:
            if marker in text:
                speaker_stats[spk]['host_markers'] += 1
                break
    
    # 选择最可能是主播的人
    best_host = None
    best_score = -1
    
    for spk, stats in speaker_stats.items():
        if spk == 'UNKNOWN':
            continue
        # 评分：host_markers权重高，其次是segment数量和总时间
        score = stats['host_markers'] * 100 + stats['count'] + stats['total_time'] / 10
        if score > best_score:
            best_score = score
            best_host = spk
    
    return best_host

def find_call_boundaries(segments, host_speaker):
    """找出连麦的开始和结束边界"""
    boundaries = []
    
    for i, seg in enumerate(segments):
        text = seg.get('text', '')
        speaker = seg.get('speaker', '')
        start = seg['start']
        
        # 连麦开始：主播说"你好"、"哈喽"等
        if speaker == host_speaker:
            if any(marker in text for marker in ['你好', '哈喽', '直接开始连麦']):
                # 检查后面是否有其他speaker
                for j in range(i+1, min(i+30, len(segments))):
                    if segments[j].get('speaker') not in [host_speaker, 'UNKNOWN']:
                        boundaries.append(('call_start', start, i, text[:40]))
                        break
        
        # 连麦结束：嘉宾说"拜拜"、"谢谢"等，且后面主播开始独白
        if speaker not in [host_speaker, 'UNKNOWN']:
            if any(marker in text for marker in ['拜拜', '谢谢', '再见']):
                # 检查后面主播是否开始独白
                host_solo = True
                for j in range(i+1, min(i+50, len(segments))):
                    next_speaker = segments[j].get('speaker')
                    if next_speaker not in [host_speaker, 'UNKNOWN']:
                        host_solo = False
                        break
                    if segments[j]['end'] - start > 30:  # 主播独白超过30秒
                        break
                
                if host_solo:
                    boundaries.append(('call_end', start, i, text[:40]))
    
    return boundaries

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 找出主播
    host_speaker = find_host(segments)
    print(f"主播识别为: {host_speaker}")
    print()
    
    # 找出连麦边界
    boundaries = find_call_boundaries(segments, host_speaker)
    
    print(f"找到 {len(boundaries)} 个边界点")
    print("\n=== 边界点详情 ===")
    
    for i, (btype, time, idx, text) in enumerate(boundaries[:50]):
        minutes = int(time // 60)
        seconds = int(time % 60)
        print(f"{i+1}. [{minutes:02d}:{seconds:02d}] {btype}: {text}")

if __name__ == '__main__':
    main()
