#!/usr/bin/env python3
"""
批量处理所有段落
"""
import subprocess
import json

# 段落定义
sections = [
    (0, 41.5, 517.0, "opening", "曲曲", "开场 - 消费升级与消费理念"),
    (1, 517.0, 920.0, "call", "嘉宾1", "第一位嘉宾 - 包包与消费"),
    (2, 920.0, 1104.0, "comment", "曲曲", "评论 - 皮质与品质"),
    (3, 1104.0, 1800.0, "call", "嘉宾2", "第二位嘉宾 - 长期关系"),
    (4, 1800.0, 2103.0, "comment", "曲曲", "评论 - 关系处理"),
    (5, 2103.0, 2587.0, "call", "嘉宾3", "第三位嘉宾 - 情感问题"),
    (6, 2587.0, 3601.0, "comment", "曲曲", "评论 - 情感建议"),
    (7, 3601.0, 4333.0, "call", "嘉宾4", "第四位嘉宾 - 职场问题"),
    (8, 4333.0, 6083.0, "comment", "曲曲", "评论 - 职场建议"),
    (9, 6083.0, 7175.0, "call", "嘉宾5", "第五位嘉宾 - 感情困惑"),
    (10, 7175.0, 8326.0, "comment", "曲曲", "评论 - 感情指导"),
    (11, 8326.0, 9386.0, "call", "嘉宾6", "第六位嘉宾 - 关系咨询"),
    (12, 9386.0, 11058.0, "comment", "曲曲", "评论 - 关系建议"),
    (13, 11058.0, 11973.0, "call", "嘉宾7", "第七位嘉宾 - 情感咨询"),
    (14, 11973.0, 12518.0, "comment", "曲曲", "评论 - 情感指导"),
    (15, 12518.0, 13182.0, "call", "嘉宾8", "第八位嘉宾 - 职场咨询"),
    (16, 13182.0, 14285.0, "comment", "曲曲", "评论 - 职场建议"),
    (17, 14285.0, 15218.6, "call", "嘉宾9", "第九位嘉宾 - 最后连麦"),
]

# 处理每个段落
input_file = "/home/duino/ws/ququ/ppl/data/03_transcripts/曲曲2024（全）/76 - 曲曲現場直播 2024年11月8日 ｜ 曲曲麥肯錫.json"

print("开始处理段落...")
for idx, start, end, kind, persona, title in sections:
    print(f"\n处理段落 {idx:02d}: {title}")
    print(f"  时间: {start:.1f}s - {end:.1f}s, 类型: {kind}")
    
    # 调用处理脚本
    cmd = [
        "python3", "/home/duino/ws/ququ/ppl/scripts/process_section.py",
        input_file,
        str(idx),
        str(start),
        str(end),
        kind,
        persona,
        title
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  错误: {result.stderr}")
    else:
        print(f"  成功: {result.stdout.strip()}")

print("\n所有段落处理完成!")
EOF