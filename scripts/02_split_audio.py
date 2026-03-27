#!/usr/bin/env python3
"""
音频文件分割工具
将 downloads/audio 下的音频文件按最长2小时分割
保持原有目录结构，输出到 audio_splits
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_audio_duration(file_path: str) -> float:
    """获取音频文件时长（秒）"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"⚠️  无法获取时长: {file_path} - {e}")
        return 0


def split_audio_file(input_file: str, output_dir: str, max_duration: int = 7200):
    """
    分割音频文件
    
    Args:
        input_file: 输入文件路径
        output_dir: 输出目录
        max_duration: 最大时长（秒），默认 2小时 = 7200秒
    """
    input_path = Path(input_file)
    duration = get_audio_duration(input_file)
    
    if duration == 0:
        print(f"❌ 跳过: {input_file} (无法获取时长)")
        return
    
    # 计算需要分割成几段
    num_parts = int(duration // max_duration) + (1 if duration % max_duration > 0 else 0)
    
    # 获取文件名（不含扩展名）
    stem = input_path.stem
    suffix = input_path.suffix
    
    print(f"📁 处理: {input_file}")
    print(f"   时长: {duration:.0f}s ({duration/3600:.1f}h)")
    print(f"   分割: {num_parts} 段")
    
    if num_parts == 1:
        # 不需要分割，直接复制
        output_file = Path(output_dir) / input_path.name
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用 ffmpeg 复制（保持质量）
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-c", "copy",
            "-metadata", f"comment=Original duration: {duration:.0f}s",
            str(output_file)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"   ✅ 复制: {output_file}")
    else:
        # 需要分割
        for i in range(num_parts):
            start_time = i * max_duration
            remaining = duration - start_time
            segment_duration = min(max_duration, remaining)
            
            # 构建输出文件名: 原文件名_part{序号}.mp3
            output_file = Path(output_dir) / f"{stem}_part{i+1:02d}{suffix}"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-ss", str(start_time),
                "-t", str(segment_duration),
                "-c", "copy",  # 复制编码，保持质量
                "-metadata", f"comment=Part {i+1}/{num_parts}, Start: {start_time}s, Duration: {segment_duration:.0f}s",
                str(output_file)
            ]
            
            print(f"   🎵 分割段 {i+1}/{num_parts}: {start_time}s ~ {start_time+segment_duration:.0f}s")
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                print(f"   ❌ 失败: {output_file}")
                print(f"      Error: {result.stderr.decode()[:200]}")
            else:
                print(f"   ✅ 保存: {output_file.name}")
    
    print()


def process_directory(input_dir: str, output_dir: str, max_duration: int = 7200):
    """
    递归处理目录下的所有音频文件
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        max_duration: 最大时长（秒）
    """
    input_path = Path(input_dir)
    audio_extensions = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
    
    # 查找所有音频文件
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(input_path.rglob(f"*{ext}"))
    
    # 按路径排序
    audio_files = sorted(audio_files)
    
    print(f"🔍 找到 {len(audio_files)} 个音频文件")
    print(f"⏱️  最大段时长: {max_duration}s ({max_duration/3600:.1f}h)")
    print(f"📂 输出目录: {output_dir}")
    print("=" * 60)
    print()
    
    # 处理每个文件
    success_count = 0
    fail_count = 0
    
    for i, audio_file in enumerate(audio_files, 1):
        # 计算相对路径，保持目录结构
        rel_path = audio_file.relative_to(input_path)
        output_subdir = Path(output_dir) / rel_path.parent
        
        print(f"[{i}/{len(audio_files)}] ", end="")
        
        try:
            split_audio_file(str(audio_file), str(output_subdir), max_duration)
            success_count += 1
        except Exception as e:
            print(f"❌ 处理失败: {audio_file}")
            print(f"   错误: {e}")
            fail_count += 1
    
    print("=" * 60)
    print(f"✅ 完成: {success_count} 个文件")
    if fail_count > 0:
        print(f"❌ 失败: {fail_count} 个文件")


def main():
    parser = argparse.ArgumentParser(
        description="音频文件分割工具 - 按时长分割并保持目录结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s downloads/audio audio_splits
  %(prog)s downloads/audio audio_splits --max-duration 3600
  %(prog)s /path/to/input /path/to/output --max-duration 7200
        """
    )
    
    parser.add_argument(
        "input_dir",
        default="data/01_downloads",
        nargs="?",
        help="输入目录 (默认: downloads/audio)"
    )
    parser.add_argument(
        "output_dir",
        default="data/02_audio_splits",
        nargs="?",
        help="输出目录 (默认: audio_splits)"
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=7200,
        help="每段最大时长（秒），默认 7200 (2小时)"
    )
    
    args = parser.parse_args()
    
    # 检查输入目录
    if not Path(args.input_dir).exists():
        print(f"❌ 输入目录不存在: {args.input_dir}")
        sys.exit(1)
    
    # 检查 ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except:
        print("❌ 需要安装 ffmpeg")
        sys.exit(1)
    
    # 创建输出目录
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # 开始处理
    process_directory(args.input_dir, args.output_dir, args.max_duration)


if __name__ == "__main__":
    main()
