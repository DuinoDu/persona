#!/usr/bin/env python3
"""
分析直播字幕文件，识别连麦段落
由于原始speaker diarization存在问题，需要基于内容重新识别
"""
import json
import os
from collections import defaultdict

def analyze_transcript(input_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data['segments']
    
    # 主播特征：通常说"宝子们"、"欢迎大家"、"你好"等
    # 嘉宾特征：自我介绍、提问、回答主播问题
    
    # 策略：
    # 1. 开场白：从开头到主播说"我们直接开始连麦了"之后
    # 2. 连麦段落：主播说"你好" + 嘉宾自我介绍 + 对话
    # 3. 评论段落：嘉宾说完"拜拜/谢谢"后，主播的独白
    
    # 首先找出所有可能的分界点
    boundaries = []
    
    for i, seg in enumerate(segments):
        text = seg.get('text', '')
        speaker = seg.get('speaker', '')
        start = seg['start']
        
        # 开场结束标记
        if '直接开始连麦了' in text or ('开始连麦' in text and '你好' in text):
            boundaries.append(('call_start', start, i, text[:50]))
        
        # 连麦结束标记（嘉宾说拜拜）
        if any(word in text for word in ['拜拜', '谢谢', '再见', '挂了']) and speaker != 'SPEAKER_02':
            boundaries.append(('call_end', start, i, text[:50]))
        
        # 新的连麦开始（主播说你好/哈喽）
        if ('你好' in text or '哈喽' in text) and speaker == 'SPEAKER_02':
            # 检查后面是否有其他speaker
            for j in range(i+1, min(i+30, len(segments))):
                if segments[j].get('speaker') not in ['SPEAKER_02', 'UNKNOWN']:
                    boundaries.append(('call_start', start, i, text[:50]))
                    break
    
    # 按时间排序
    boundaries.sort(key=lambda x: x[1])
    
    return boundaries, segments

def main():
    input_file = '/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/37 - 曲曲直播未删减修复版 2024年06月25日 高清分章节版 #曲曲麦肯锡.json'
    
    boundaries, segments = analyze_transcript(input_file)
    
    print(f"找到 {len(boundaries)} 个边界点")
    print("\n=== 前30个边界点 ===")
    
    for i, (btype, time, idx, text) in enumerate(boundaries[:30]):
        minutes = int(time // 60)
        seconds = int(time % 60)
        print(f"{i+1}. [{minutes:02d}:{seconds:02d}] {btype}: {text}")

if __name__ == '__main__':
    main()
