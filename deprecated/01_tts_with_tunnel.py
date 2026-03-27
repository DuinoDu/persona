#!/usr/bin/env python3
"""
使用 Cloudflare Tunnel 处理本地音频文件的 TTS 工具
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
import requests

# API 配置
API_TOKEN = "wx9x920cn51c8t1ye"
CREATE_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition"
QUERY_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition/{task_id}"


def start_cloudflare_tunnel(local_port):
    """启动 Cloudflare Tunnel 并返回公网 URL"""
    print("🌐 启动 Cloudflare Tunnel...")
    
    cmd = [
        str(Path.home() / ".local" / "bin" / "cloudflared"),
        "tunnel",
        "--url", f"http://localhost:{local_port}"
    ]
    
    # 启动 tunnel 进程
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # 等待并提取 URL
    public_url = None
    for _ in range(60):  # 最多等待 60 秒
        line = process.stdout.readline()
        if line:
            print(f"   {line.strip()}")
            # 提取 https://xxx.trycloudflare.com
            if "trycloudflare.com" in line:
                import re
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if match:
                    public_url = match.group(0)
                    break
        time.sleep(0.5)
    
    if not public_url:
        process.terminate()
        raise Exception("无法获取 Cloudflare Tunnel URL")
    
    print(f"✅ Tunnel 已建立: {public_url}")
    return process, public_url


def start_file_server(directory, port):
    """启动简单的 HTTP 文件服务器"""
    import http.server
    import socketserver
    import threading
    
    os.chdir(directory)
    handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("", port), handler)
    
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    
    return httpd


def create_task(url, language="zh", speaker_recognition=True):
    """创建语音识别任务"""
    headers = {
        "X-API-Key": API_TOKEN,
        "Content-Type": "application/json",
    }
    
    payload = {
        "url": url,
        "type": 4,
        "speaker_recognition": 1 if speaker_recognition else 0,
    }
    
    if language:
        payload["language"] = language
    
    response = requests.post(CREATE_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    if data.get("status") != 200:
        raise Exception(f"API 错误: {data.get('message')}")
    
    return data["data"]["task_id"]


def query_task(task_id):
    """查询任务状态"""
    headers = {"X-API-Key": API_TOKEN}
    url = QUERY_API_URL.format(task_id=task_id)
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    if data.get("status") != 200:
        raise Exception(f"API 错误: {data.get('message')}")
    
    return data["data"]


def wait_for_result(task_id, poll_interval=5):
    """等待任务完成"""
    print("⏳ 等待处理完成...")
    
    while True:
        data = query_task(task_id)
        state = data.get("state")
        progress = data.get("progress", 0)
        state_detail = data.get("state_detail", "")
        
        print(f"   状态: {state_detail} | 进度: {progress}%", end="\r")
        
        if state == 1:
            print(f"\n✅ 处理完成！")
            return data
        
        if state < 0:
            raise Exception(f"任务失败: {state_detail}")
        
        time.sleep(poll_interval)


def format_result(data, output_format="text"):
    """格式化结果"""
    result = data.get("result", [])
    source_language = data.get("source_language", "unknown")
    duration = data.get("duration", 0)
    
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    if output_format == "srt":
        lines = []
        for i, item in enumerate(result, 1):
            start_ms = item.get("start", 0)
            end_ms = item.get("end", 0)
            text = item.get("text", "").strip()
            speaker = item.get("speaker", "未知")
            
            start_srt = ms_to_srt_time(start_ms)
            end_srt = ms_to_srt_time(end_ms)
            
            lines.append(str(i))
            lines.append(f"{start_srt} --> {end_srt}")
            lines.append(f"[{speaker}] {text}")
            lines.append("")
        return "\n".join(lines)
    
    # Text format
    lines = []
    lines.append(f"# 语音识别结果")
    lines.append(f"# 源语言: {source_language}")
    lines.append(f"# 时长: {duration} 秒")
    lines.append(f"# 片段数: {len(result)}")
    lines.append("")
    
    current_speaker = None
    for item in result:
        start_ms = item.get("start", 0)
        end_ms = item.get("end", 0)
        text = item.get("text", "").strip()
        speaker = item.get("speaker", "未知")
        
        start_time = ms_to_time(start_ms)
        end_time = ms_to_time(end_ms)
        
        if speaker != current_speaker:
            lines.append(f"\n[{speaker}] {start_time} - {end_time}")
            current_speaker = speaker
        else:
            lines.append(f"[{start_time} - {end_time}]")
        
        lines.append(f"{text}\n")
    
    return "\n".join(lines)


def ms_to_time(ms):
    """毫秒转时间格式"""
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def ms_to_srt_time(ms):
    """毫秒转 SRT 时间格式"""
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    parser = argparse.ArgumentParser(
        description="使用 Cloudflare Tunnel 处理本地音频文件的 TTS 工具"
    )
    parser.add_argument("file", help="本地音频文件路径")
    parser.add_argument("-l", "--language", default="zh", help="输出语言")
    parser.add_argument("-o", "--output", default=None, help="输出文件路径")
    parser.add_argument("-f", "--format", choices=["text", "json", "srt"], default="text")
    parser.add_argument("--no-speaker", action="store_true", help="关闭说话人识别")
    parser.add_argument("--local-port", type=int, default=8765, help="本地服务器端口")
    
    args = parser.parse_args()
    
    # 检查文件
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)
    
    print(f"📁 文件: {file_path.name}")
    print(f"📊 大小: {file_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    # 保存原始目录
    original_dir = os.getcwd()
    file_dir = file_path.parent
    filename = urllib.parse.quote(file_path.name)
    
    # 启动本地文件服务器
    print(f"🚀 启动本地文件服务器 (端口 {args.local_port})...")
    server = start_file_server(str(file_dir), args.local_port)
    
    # 启动 Cloudflare Tunnel
    tunnel_process = None
    try:
        tunnel_process, public_url = start_cloudflare_tunnel(args.local_port)
        file_url = f"{public_url}/{filename}"
        print(f"🌐 文件公网地址: {file_url}")
        
        # 等待几秒让 tunnel 稳定
        time.sleep(3)
        
        # 创建 TTS 任务
        print("🎙️  创建语音识别任务...")
        task_id = create_task(
            file_url,
            language=args.language,
            speaker_recognition=not args.no_speaker
        )
        print(f"✅ 任务创建成功: {task_id}")
        
        # 等待结果
        result_data = wait_for_result(task_id)
        
        # 格式化输出
        output = format_result(result_data, output_format=args.format)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"✅ 结果已保存到: {args.output}")
        else:
            print("\n" + "=" * 60)
            print(output)
            print("=" * 60)
    
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)
    finally:
        # 清理
        print("🛑 清理资源...")
        if tunnel_process:
            tunnel_process.terminate()
        server.shutdown()
        os.chdir(original_dir)


if __name__ == "__main__":
    import json
    main()
