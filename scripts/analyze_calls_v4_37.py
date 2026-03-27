#!/usr/bin/env python3
"""
分析直播字幕文件，识别连麦段落 - v4

核心观察：
- 主播是SPEAKER_02（通过"宝子们"、"欢迎大家"等词汇识别）
- 每次连麦结构：主播说"你好" → 嘉宾自我介绍 → 问答对话 → 嘉宾说"拜拜" → 主播评论
- 需要识别主播和嘉宾交替说话的模式
"""
import json
from collections import defaultdict

def format_time(seconds):
    """格式化时间为 MM:SS"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def analyze_speakers(segments):
    """分析speaker特征，找出主播"""
    speaker_stats = defaultdict(lambda: {'count': 0, 'markers': 0, 'texts': []})
    
    host_markers = ['宝子们', '欢迎大家', '我们直接开始连麦', '每人解忧铺']
    
    for seg in segments[:1000]:  # 只看前1000个segment
        spk = seg.get('speaker', 'UNKNOWN')
        text = seg.get('text', '')
        speaker_stats[spk]['count'] += 1
        speaker_stats[spk]['texts'].append(text[:30])
        
        for marker in host_markers:
            if marker in text:
                speaker_stats[spk]['markers'] += 1
    
    # 选择最可能是主播的人
    best_host = None
    best_score = -1
    
    for spk, stats in speaker_stats.items():
        if spk == 'UNKNOWN':
            continue
        score = stats['markers'] * 10 + stats['count']
        if score > best_score:
            best_score = score
            best_host = spk
    
    return best_host, speaker_stats

def find_calls(segments, host_speaker):
    """找出所有连麦段落"""
    calls = []
    
    # 找到开场结束点（主播说"直接开始连麦"）
    opening_end_idx = 0
    for i, seg in enumerate(segments):
        if seg.get('speaker') == host_speaker:
            if '直接开始连麦' in seg.get('text', ''):
                opening_end_idx = i
                break
    
    opening_end_time = segments[opening_end_idx]['end']
    print(f"开场结束: {format_time(opening_end_time)} (segment {opening_end_idx})")
    
    # 从开场结束后开始找连麦
    i = opening_end_idx + 1
    call_num = 0
    
    while i < len(segments):
        seg = segments[i]
        text = seg.get('text', '')
        speaker = seg.get('speaker', '')
        
        # 寻找连麦开始：主播说"你好"、"哈喽"等，且后面有嘉宾说话
        if speaker == host_speaker and any(m in text for m in ['你好', '哈喽']):
            # 向前看，找是否有嘉宾说话
            guest_start = None
            for j in range(i+1, min(i+50, len(segments))):
                if segments[j].get('speaker') not in [host_speaker, 'UNKNOWN']:
                    guest_start = j
                    break
            
            if guest_start:
                # 找到连麦开始，现在找结束
                call_start_idx = i
                call_end_idx = guest_start
                
                # 继续找这个连麦的结束
                for j in range(guest_start, min(guest_start + 2000, len(segments))):
                    # 检测连麦结束：嘉宾说拜拜，或者长时间没有嘉宾说话
                    seg_j = segments[j]
                    if seg_j.get('speaker') not in [host_speaker, 'UNKNOWN']:
                        call_end_idx = j
                        text_j = seg_j.get('text', '')
                        if any(m in text_j for m in ['拜拜', '再见']) and len(text_j) < 20:
                            # 连麦可能结束，检查后面主播是否独白
                            host_solo = True
                            for k in range(j+1, min(j+50, len(segments))):
                                if segments[k].get('speaker') not in [host_speaker, 'UNKNOWN']:
                                    host_solo = False
                                    break
                            if host_solo:
                                call_end_idx = j
                                break
                
                call_num += 1
                start_time = segments[call_start_idx]['start']
                end_time = segments[call_end_idx]['end']
                duration = (end_time - start_time) / 60
                
                # 找出这个连麦中涉及的嘉宾
                guests = set()
                for k in range(call_start_idx, call_end_idx + 1):
                    spk = segments[k].get('speaker')
                    if spk not in [host_speaker, 'UNKNOWN']:
                        guests.add(spk)
                
                calls.append({
                    'num': call_num,
                    'start_idx': call_start_idx,
                    'end_idx': call_end_idx,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'guests': list(guests)
                })
                
                print(f"连麦{call_num}: {format_time(start_time)} - {format_time(end_time)}, "
                      f"持续={duration:.1f}分钟, 嘉宾={guests}")
                
                i = call_end_idx + 1
                continue
        
        i += 1
    
    return calls, opening_end_time

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 分析speaker
    host_speaker, speaker_stats = analyze_speakers(segments)
    print(f"主播识别为: {host_speaker}")
    print(f"\nSpeaker统计:")
    for spk, stats in sorted(speaker_stats.items(), key=lambda x: -x[1]['count']):
        print(f"  {spk}: count={stats['count']}, markers={stats['markers']}")
    print()
    
    # 找出连麦
    calls, opening_end = find_calls(segments, host_speaker)
    
    print(f"\n共找到 {len(calls)} 次连麦")

if __name__ == '__main__':
    main()
