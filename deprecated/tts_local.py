#!/usr/bin/env python3
"""
处理本地音频文件的 TTS 工具
自动启动临时 HTTP 服务器来提供本地文件给 RecCloud API
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import socket


def get_local_ip():
    """获取本机 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def find_free_port(start=8000, end=9000):
    """查找可用端口"""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except:
            continue
    raise Exception("No free port found")


def start_file_server(directory, port):
    """启动文件服务器"""
    os.chdir(directory)
    server = HTTPServer(("", port), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    parser = argparse.ArgumentParser(
        description="处理本地音频文件的语音转文本工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "/path/to/audio.mp3"
  %(prog)s "/path/to/audio.mp3" -l zh -o result.txt
  %(prog)s "/path/to/audio.mp3" -f srt -o subtitle.srt
        """,
    )

    parser.add_argument("file", help="本地音频文件路径")
    parser.add_argument(
        "-l", "--language",
        default="zh",
        help="输出语言 (默认: zh)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出文件路径，默认输出到控制台"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["text", "json", "srt"],
        default="text",
        help="输出格式 (默认: text)"
    )
    parser.add_argument(
        "--no-speaker",
        action="store_true",
        help="关闭说话人识别"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP 服务器端口 (默认: 自动选择)"
    )

    args = parser.parse_args()

    # 检查文件
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)

    file_size_mb = file_path.stat().st_size / 1024 / 1024
    print(f"📁 文件: {file_path.name}")
    print(f"📊 大小: {file_size_mb:.1f} MB")

    # 准备 HTTP 服务器
    directory = file_path.parent
    filename = urllib.parse.quote(file_path.name)

    # 查找可用端口
    port = args.port or find_free_port()
    ip = get_local_ip()

    # 构建 URL
    url = f"http://{ip}:{port}/{filename}"
    print(f"🌐 临时文件服务器: {url}")

    # 启动服务器
    print(f"🚀 启动 HTTP 服务器 (端口 {port})...")
    original_dir = os.getcwd()
    server = start_file_server(str(directory), port)

    # 等待服务器启动
    time.sleep(1)

    try:
        # 调用 tts.py (使用绝对路径)
        print("🎙️  开始语音识别...")
        script_dir = Path(__file__).parent.resolve()
        tts_script = script_dir / "tts.py"
        
        cmd = [
            sys.executable, str(tts_script),
            url,
            "-l", args.language,
            "-f", args.format,
        ]

        if args.output:
            cmd.extend(["-o", args.output])

        if args.no_speaker:
            cmd.append("--no-speaker")

        result = subprocess.run(cmd, capture_output=False)

        if result.returncode != 0:
            print("❌ TTS 处理失败")
            sys.exit(1)

    finally:
        # 关闭服务器
        print("🛑 关闭 HTTP 服务器...")
        server.shutdown()
        os.chdir(original_dir)

    print("✅ 完成！")


if __name__ == "__main__":
    main()
