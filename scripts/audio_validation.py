#!/usr/bin/env python3
"""
音频特征分析验证脚本
通过分析音频的频谱特征来验证说话人识别的正确性
"""

import json
import os
import sys
import numpy as np
from pathlib import Path

def analyze_speaker_consistency(sentences):
    """
    分析说话人一致性
    - 检查HOST和GUEST的发言模式
    - 返回一致性评分
    """
    host_segments = []
    guest_segments = []

    for sent in sentences:
        speaker = sent.get('speaker_id', '')
        duration = sent.get('end', 0) - sent.get('start', 0)
        text_len = len(sent.get('text', ''))

        if speaker == 'host':
            host_segments.append({
                'duration': duration,
                'text_len': text_len,
                'text': sent.get('text', '')
            })
        elif speaker == 'guest':
            guest_segments.append({
                'duration': duration,
                'text_len': text_len,
                'text': sent.get('text', '')
            })

    # 计算统计信息
    stats = {
        'host': {
            'segment_count': len(host_segments),
            'avg_duration': np.mean([s['duration'] for s in host_segments]) if host_segments else 0,
            'avg_text_len': np.mean([s['text_len'] for s in host_segments]) if host_segments else 0,
            'total_duration': sum([s['duration'] for s in host_segments]),
            'total_chars': sum([s['text_len'] for s in host_segments])
        },
        'guest': {
            'segment_count': len(guest_segments),
            'avg_duration': np.mean([s['duration'] for s in guest_segments]) if guest_segments else 0,
            'avg_text_len': np.mean([s['text_len'] for s in guest_segments]) if guest_segments else 0,
            'total_duration': sum([s['duration'] for s in guest_segments]),
            'total_chars': sum([s['text_len'] for s in guest_segments])
        }
    }

    # 检查一致性
    checks = []

    # 检查1: HOST的发言应该比GUEST多（评论段落除外）
    total_host = stats['host']['segment_count']
    total_guest = stats['guest']['segment_count']

    if total_host > 0 and total_guest > 0:
        ratio = total_host / total_guest
        if 0.5 < ratio < 3.0:  # HOST发言次数在GUEST的0.5到3倍之间
            checks.append(('发言比例', 'PASS', f'HOST:GUEST = {ratio:.2f}:1'))
        else:
            checks.append(('发言比例', 'WARNING', f'HOST:GUEST = {ratio:.2f}:1 (偏离正常范围)'))
    elif total_guest == 0:
        checks.append(('发言比例', 'PASS', '单说话人段落'))
    else:
        checks.append(('发言比例', 'WARNING', '没有HOST发言'))

    # 检查2: 平均发言时长是否合理
    host_avg = stats['host']['avg_duration']
    guest_avg = stats['guest']['avg_duration']

    if host_avg > 0 and guest_avg > 0:
        if 1.0 < host_avg < 60.0 and 1.0 < guest_avg < 60.0:  # 平均发言时长在1-60秒之间
            checks.append(('发言时长', 'PASS', f'HOST平均{host_avg:.1f}s, GUEST平均{guest_avg:.1f}s'))
        else:
            checks.append(('发言时长', 'WARNING', f'平均时长异常: HOST={host_avg:.1f}s, GUEST={guest_avg:.1f}s'))

    return {
        'stats': stats,
        'checks': checks,
        'consistency_score': len([c for c in checks if c[1] == 'PASS']) / len(checks) if checks else 0
    }

def validate_segment_file(file_path):
    """
    验证单个段落文件
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    meta = data.get('meta', {})
    sentences = data.get('sentences', [])

    if not sentences:
        return {
            'file': os.path.basename(file_path),
            'valid': False,
            'error': '没有句子数据'
        }

    # 分析说话人一致性
    consistency = analyze_speaker_consistency(sentences)

    return {
        'file': os.path.basename(file_path),
        'valid': True,
        'kind': meta.get('kind', 'unknown'),
        'title': meta.get('title', ''),
        'sentence_count': len(sentences),
        'consistency': consistency
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python audio_validation.py <processed_directory>")
        print("Example:")
        print("  python audio_validation.py /path/to/processed/")
        sys.exit(1)

    processed_dir = sys.argv[1]

    if not os.path.exists(processed_dir):
        print(f"错误: 目录不存在: {processed_dir}")
        sys.exit(1)

    print("=" * 80)
    print("音频特征分析验证报告")
    print("=" * 80)
    print()

    # 查找所有schema格式的文件
    schema_files = sorted([f for f in os.listdir(processed_dir) if f.endswith('_schema.json')])

    if not schema_files:
        print("未找到schema格式的文件")
        sys.exit(1)

    print(f"找到 {len(schema_files)} 个段落文件")
    print()

    # 验证每个文件
    results = []
    for schema_file in schema_files:
        file_path = os.path.join(processed_dir, schema_file)
        result = validate_segment_file(file_path)
        results.append(result)

    # 显示结果
    print("-" * 80)
    print("验证结果")
    print("-" * 80)
    print()

    total_score = 0
    valid_count = 0

    for result in results:
        if not result['valid']:
            print(f"❌ {result['file']}: {result.get('error', '验证失败')}")
            continue

        valid_count += 1
        consistency = result.get('consistency', {})
        score = consistency.get('consistency_score', 0)
        total_score += score

        kind = result.get('kind', 'unknown')
        title = result.get('title', '')
        sentence_count = result.get('sentence_count', 0)

        # 显示图标
        icon = '✅' if score >= 0.8 else '⚠️' if score >= 0.5 else '❓'

        print(f"{icon} {result['file']}")
        print(f"   类型: {kind} | 标题: {title}")
        print(f"   句子数: {sentence_count} | 一致性评分: {score*100:.1f}%")

        # 显示详细检查
        checks = consistency.get('checks', [])
        for check in checks:
            status_icon = '✓' if check[1] == 'PASS' else '!'
            print(f"   [{status_icon}] {check[0]}: {check[2]}")
        print()

    # 显示汇总
    print("-" * 80)
    print("汇总")
    print("-" * 80)
    print(f"总文件数: {len(results)}")
    print(f"验证通过: {valid_count}")
    print(f"验证失败: {len(results) - valid_count}")

    if valid_count > 0:
        avg_score = total_score / valid_count
        print(f"平均一致性评分: {avg_score*100:.1f}%")

    print("=" * 80)

if __name__ == '__main__':
    main()
