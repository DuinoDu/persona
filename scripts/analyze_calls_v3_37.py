#!/usr/bin/env python3
"""
分析直播字幕文件，识别连麦段落 - 修正版
基于主播的语言特征来识别
"""
import json
import os
from collections import defaultdict

def find_host_by_content(segments):
    """通过内容特征找出主播
    
    主播通常会说：
    - "宝子们"
    - "欢迎大家" 
    - "我们直接开始连麦"
    - "每人解忧铺"
    """
    speaker_scores = defaultdict(int)
    
    host_markers = {
        '宝子们': 10,
        '欢迎大家': 5,
        '我们直接开始连麦': 20,
        '每人解忧铺': 10,
        '哈喽你好': 5,
        '你好，你说': 5,
    }
    
    for seg in segments:
        spk = seg.get('speaker', 'UNKNOWN')
        if spk == 'UNKNOWN':
            continue
        text = seg.get('text', '')
        
        for marker, score in host_markers.items():
            if marker in text:
                speaker_scores[spk] += score
    
    # 选择分数最高的作为主播
    if speaker_scores:
        host = max(speaker_scores.items(), key=lambda x: x[1])[0]
        print(f"Speaker分数: {dict(speaker_scores)}")
        return host
    return None

def identify_calls(segments, host_speaker):
    """识别连麦段落
    
    策略：
    1. 开场：从开头到第一个主播说"直接开始连麦"
    2. 每次连麦：从主播说"你好"开始，到嘉宾说"拜拜/谢谢"结束
    3. 评论：连麦结束后主播的独白
    """
    
    # 状态机
    STATE_OPENING = 'opening'
    STATE_CALL = 'call'
    STATE_COMMENT = 'comment'
    
    state = STATE_OPENING
    calls = []
    current_call_start = None
    current_call_segments = []
    
    opening_end = None
    
    for i, seg in enumerate(segments):
        text = seg.get('text', '')
        speaker = seg.get('speaker', '')
        
        # 检测连麦开始（主播说"你好"或"直接开始连麦"）
        if state == STATE_OPENING:
            if speaker == host_speaker and ('直接开始连麦' in text or ('你好' in text and '大家好' not in text)):
                opening_end = seg['start']
                state = STATE_CALL
                current_call_start = i
                current_call_segments = [seg]
        
        elif state == STATE_CALL:
            current_call_segments.append(seg)
            
            # 检测连麦结束（嘉宾说"拜拜"、"谢谢"等，且后面主播开始独白）
            if speaker != host_speaker and speaker != 'UNKNOWN':
                if any(word in text for word in ['拜拜', '谢谢', '再见']):
                    # 检查后面主播是否开始独白
                    host_solo_count = 0
                    guest_count = 0
                    for j in range(i+1, min(i+30, len(segments))):
                        next_speaker = segments[j].get('speaker')
                        if next_speaker == host_speaker:
                            host_solo_count += 1
                        elif next_speaker not in [host_speaker, 'UNKNOWN']:
                            guest_count += 1
                            break
                    
                    if host_solo_count > 5 and guest_count == 0:
                        # 连麦结束
                        calls.append({
                            'start_idx': current_call_start,
                            'end_idx': i,
                            'start_time': segments[current_call_start]['start'],
                            'end_time': seg['end'],
                            'segments': current_call_segments
                        })
                        state = STATE_COMMENT
                        current_call_segments = []
        
        elif state == STATE_COMMENT:
            # 评论状态，等待下一个连麦开始
            if speaker == host_speaker and ('你好' in text or '哈喽' in text):
                # 检查后面是否有嘉宾
                for j in range(i+1, min(i+30, len(segments))):
                    if segments[j].get('speaker') not in [host_speaker, 'UNKNOWN']:
                        state = STATE_CALL
                        current_call_start = i
                        current_call_segments = [seg]
                        break
    
    return {
        'opening_end': opening_end,
        'calls': calls
    }

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    
    print(f"总segment数: {len(segments)}")
    print()
    
    # 找出主播
    host_speaker = find_host_by_content(segments)
    print(f"\n主播识别为: {host_speaker}")
    print()
    
    # 识别连麦
    result = identify_calls(segments, host_speaker)
    
    print(f"开场结束时间: {result['opening_end']:.2f}s ({int(result['opening_end']//60)}:{int(result['opening_end']%60):02d})")
    print(f"检测到连麦次数: {len(result['calls'])}")
    print()
    
    for i, call in enumerate(result['calls'][:10]):  # 只显示前10个
        start = call['start_time']
        end = call['end_time']
        duration = (end - start) / 60
        
        start_min = int(start // 60)
        start_sec = int(start % 60)
        end_min = int(end // 60)
        end_sec = int(end % 60)
        
        print(f"连麦{i+1}: [{start_min:02d}:{start_sec:02d}] - [{end_min:02d}:{end_sec:02d}], 持续={duration:.1f}分钟, segments={len(call['segments'])}")

if __name__ == '__main__':
    main()
