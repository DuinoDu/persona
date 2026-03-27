#!/usr/bin/env python3
"""
TTS 处理器 - 自动管理 Tunnel 和批量处理
"""

import json
import os
import requests
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from datetime import datetime

# API 配置
API_TOKEN = "wx9x920cn51c8t1ye"
CREATE_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition"
QUERY_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition/{task_id}"


class TTSProcessor:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 已处理记录
        self.record_file = self.output_dir / ".processed.json"
        self.processed = self._load_processed()
        
        # 统计
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0
    
    def _load_processed(self):
        if self.record_file.exists():
            try:
                with open(self.record_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_processed(self):
        with open(self.record_file, 'w') as f:
            json.dump(self.processed, f, ensure_ascii=False, indent=2)
    
    def get_mp3_files(self):
        """获取所有 MP3 文件"""
        files = sorted(self.input_dir.rglob("*.mp3"))
        return files
    
    def start_services(self):
        """启动 HTTP 服务器和 Cloudflare Tunnel"""
        print("🚀 启动服务...")
        
        # 查找可用端口
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        
        # 启动 HTTP 服务器
        http_cmd = [
            sys.executable, "-m", "http.server", str(port),
            "--directory", str(self.input_dir)
        ]
        self.http_proc = subprocess.Popen(
            http_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"   HTTP Server: port {port}, PID {self.http_proc.pid}")
        time.sleep(2)
        
        # 启动 Cloudflare Tunnel
        cloudflared_path = Path.home() / ".local" / "bin" / "cloudflared"
        tunnel_cmd = [str(cloudflared_path), "tunnel", "--url", f"http://localhost:{port}"]
        
        self.tunnel_log = f"/tmp/tunnel_{int(time.time())}.log"
        with open(self.tunnel_log, 'w') as log_file:
            self.tunnel_proc = subprocess.Popen(
                tunnel_cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT
            )
        
        print(f"   Tunnel: PID {self.tunnel_proc.pid}")
        
        # 等待获取 URL
        print("   等待 tunnel 就绪...")
        self.tunnel_url = None
        for i in range(60):
            time.sleep(1)
            if os.path.exists(self.tunnel_log):
                with open(self.tunnel_log, 'r') as f:
                    content = f.read()
                    import re
                    match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
                    if match:
                        self.tunnel_url = match.group(0)
                        break
            print(f"\r   等待... {i+1}s", end="", flush=True)
        
        print()
        if not self.tunnel_url:
            raise Exception("无法获取 tunnel URL")
        
        print(f"   ✅ Tunnel URL: {self.tunnel_url}")
        time.sleep(3)  # 等待 tunnel 完全就绪
    
    def stop_services(self):
        """停止服务"""
        print("\n🛑 停止服务...")
        if hasattr(self, 'tunnel_proc') and self.tunnel_proc:
            self.tunnel_proc.terminate()
            try:
                self.tunnel_proc.wait(timeout=5)
            except:
                self.tunnel_proc.kill()
        
        if hasattr(self, 'http_proc') and self.http_proc:
            self.http_proc.terminate()
            try:
                self.http_proc.wait(timeout=5)
            except:
                self.http_proc.kill()
        
        # 清理日志
        if hasattr(self, 'tunnel_log') and os.path.exists(self.tunnel_log):
            os.remove(self.tunnel_log)
    
    def process_single_file(self, mp3_file: Path) -> bool:
        """处理单个文件"""
        rel_path = mp3_file.relative_to(self.input_dir)
        output_file = self.output_dir / rel_path.with_suffix('.txt')
        
        file_id = str(rel_path)
        
        # 检查是否已处理
        if file_id in self.processed:
            print(f"⏭️  跳过: {rel_path}")
            self.skip_count += 1
            return True
        
        # 构建 URL
        encoded_path = '/'.join(urllib.parse.quote(part) for part in rel_path.parts)
        file_url = f"{self.tunnel_url}/{encoded_path}"
        
        print(f"\n🎙️  处理: {rel_path}")
        print(f"   URL: {file_url[:60]}...")
        
        try:
            # 创建任务
            headers = {"X-API-Key": API_TOKEN, "Content-Type": "application/json"}
            payload = {
                "url": file_url,
                "type": 4,
                "speaker_recognition": 1,
                "language": "zh"
            }
            
            resp = requests.post(CREATE_API_URL, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") != 200:
                raise Exception(data.get("message"))
            
            task_id = data["data"]["task_id"]
            print(f"   Task ID: {task_id}")
            
            # 等待结果
            print(f"   处理中...", end="", flush=True)
            while True:
                query_resp = requests.get(
                    QUERY_API_URL.format(task_id=task_id),
                    headers=headers,
                    timeout=30
                )
                query_resp.raise_for_status()
                result_data = query_resp.json()["data"]
                
                state = result_data.get("state")
                progress = result_data.get("progress", 0)
                
                print(f"\r   进度: {progress}%", end="", flush=True)
                
                if state == 1:
                    print(f"\r   ✅ 完成! {len(result_data.get('result', []))} 片段")
                    break
                
                if state < 0:
                    raise Exception(f"任务失败: {result_data.get('state_detail')}")
                
                time.sleep(5)
            
            # 格式化并保存结果
            text = self._format_result(result_data)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text)
            
            print(f"   💾 保存: {output_file}")
            
            # 记录
            self.processed[file_id] = {
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "output": str(output_file)
            }
            self._save_processed()
            
            self.success_count += 1
            return True
            
        except Exception as e:
            print(f"\n   ❌ 失败: {e}")
            self.fail_count += 1
            return False
    
    def _format_result(self, data: dict) -> str:
        """格式化结果"""
        result = data.get("result", [])
        source_language = data.get("source_language", "unknown")
        duration = data.get("duration", 0)
        
        lines = [
            f"# 语音识别结果",
            f"# 源语言: {source_language}",
            f"# 时长: {duration} 秒",
            f"# 片段数: {len(result)}",
            ""
        ]
        
        current_speaker = None
        for item in result:
            start_ms = item.get("start", 0)
            end_ms = item.get("end", 0)
            text = item.get("text", "").strip()
            speaker = item.get("speaker", "未知")
            
            def ms_to_time(ms):
                seconds = ms // 1000
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                return f"{hours:02d}:{minutes:02d}:{secs:02d}"
            
            start_time = ms_to_time(start_ms)
            end_time = ms_to_time(end_ms)
            
            if speaker != current_speaker:
                lines.append(f"\n[{speaker}] {start_time} - {end_time}")
                current_speaker = speaker
            else:
                lines.append(f"[{start_time} - {end_time}]")
            
            lines.append(f"{text}\n")
        
        return "\n".join(lines)
    
    def run(self, max_files: int = None):
        """运行批量处理"""
        files = self.get_mp3_files()
        total = len(files)
        
        print(f"🔍 找到 {total} 个 MP3 文件")
        print(f"📂 输入: {self.input_dir}")
        print(f"📂 输出: {self.output_dir}")
        print("=" * 60)
        
        if max_files:
            files = files[:max_files]
            print(f"⚠️  仅处理前 {max_files} 个文件\n")
        
        try:
            # 启动服务
            self.start_services()
            
            # 处理文件
            for i, mp3_file in enumerate(files, 1):
                print(f"\n[{i}/{len(files)}]", end=" ")
                self.process_single_file(mp3_file)
                
                # 避免 API 限流
                if i < len(files):
                    time.sleep(3)
            
        finally:
            # 确保服务停止
            self.stop_services()
        
        # 统计
        print("\n" + "=" * 60)
        print("📊 处理完成:")
        print(f"   ✅ 成功: {self.success_count}")
        print(f"   ⏭️  跳过: {self.skip_count}")
        print(f"   ❌ 失败: {self.fail_count}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="批量音频转文本")
    parser.add_argument("--input", default="audio_splits", help="输入目录")
    parser.add_argument("--output", default="01_stt", help="输出目录")
    parser.add_argument("--max-files", type=int, default=None, help="最大处理文件数")
    
    args = parser.parse_args()
    
    processor = TTSProcessor(args.input, args.output)
    processor.run(max_files=args.max_files)


if __name__ == "__main__":
    main()
