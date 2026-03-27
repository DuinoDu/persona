#!/usr/bin/env python3
"""
批量音频转文本工具 - STT (Speech To Text)
处理 00_audio_splits 下的所有 MP3 文件，保持目录结构保存到 01_stt
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from datetime import datetime
import requests

# API 配置
API_TOKEN = "wx9x920cn51c8t1ye"
CREATE_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition"
QUERY_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition/{task_id}"


class BatchSTTProcessor:
    def __init__(self, input_dir: str, output_dir: str, tunnel_url: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.tunnel_url = tunnel_url.rstrip('/')
        self.headers = {
            "X-API-Key": API_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.processed_count = 0
        self.failed_count = 0
        self.skip_count = 0
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载已处理记录
        self.record_file = self.output_dir / ".processed.json"
        self.processed_files = self._load_processed()
    
    def _load_processed(self) -> dict:
        """加载已处理文件记录"""
        if self.record_file.exists():
            try:
                with open(self.record_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_processed(self):
        """保存已处理文件记录"""
        with open(self.record_file, 'w', encoding='utf-8') as f:
            json.dump(self.processed_files, f, ensure_ascii=False, indent=2)
    
    def get_all_mp3_files(self) -> list:
        """获取所有 MP3 文件"""
        files = list(self.input_dir.rglob("*.mp3"))
        return sorted(files)
    
    def create_task(self, file_url: str, language: str = "zh") -> str:
        """创建语音识别任务"""
        payload = {
            "url": file_url,
            "type": 4,
            "speaker_recognition": 1,
            "language": language,
        }
        
        response = requests.post(
            CREATE_API_URL,
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != 200:
            raise Exception(f"API 错误: {data.get('message')}")
        
        return data["data"]["task_id"]
    
    def query_task(self, task_id: str) -> dict:
        """查询任务状态"""
        url = QUERY_API_URL.format(task_id=task_id)
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != 200:
            raise Exception(f"API 错误: {data.get('message')}")
        
        return data["data"]
    
    def wait_for_result(self, task_id: str, poll_interval: int = 5, timeout: int = 1800) -> dict:
        """等待任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            data = self.query_task(task_id)
            state = data.get("state")
            progress = data.get("progress", 0)
            state_detail = data.get("state_detail", "")
            
            if state == 1:
                return data
            
            if state < 0:
                raise Exception(f"任务失败: {state_detail}")
            
            print(f"\r   进度: {progress}% ({state_detail})", end="", flush=True)
            time.sleep(poll_interval)
        
        raise Exception("等待超时")
    
    def format_result(self, data: dict) -> str:
        """格式化结果为文本"""
        result = data.get("result", [])
        source_language = data.get("source_language", "unknown")
        duration = data.get("duration", 0)
        
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
            
            # 转换时间
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
    
    def process_file(self, mp3_file: Path) -> bool:
        """处理单个 MP3 文件"""
        # 计算相对路径
        rel_path = mp3_file.relative_to(self.input_dir)
        
        # 构建输出文件路径（将 .mp3 替换为 .txt）
        output_file = self.output_dir / rel_path.with_suffix('.txt')
        
        # 检查是否已处理
        file_id = str(rel_path)
        if file_id in self.processed_files:
            print(f"⏭️  跳过（已处理）: {rel_path}")
            self.skip_count += 1
            return True
        
        # 构建文件 URL - 包含子目录路径
        # 获取相对于 input_dir 的父目录路径
        rel_parent = rel_path.parent
        encoded_name = urllib.parse.quote(mp3_file.name)
        
        # 构建完整的 URL 路径
        if str(rel_parent) != ".":
            # 有子目录，需要编码子目录路径
            encoded_parent = "/".join(
                urllib.parse.quote(part) for part in rel_parent.parts
            )
            file_url = f"{self.tunnel_url}/{encoded_parent}/{encoded_name}"
        else:
            file_url = f"{self.tunnel_url}/{encoded_name}"
        
        print(f"\n🎙️  处理 [{self.processed_count + self.failed_count + self.skip_count + 1}]: {rel_path}")
        print(f"   URL: {file_url[:100]}...")
        
        try:
            # 创建任务
            print(f"   创建任务...", end=" ")
            task_id = self.create_task(file_url)
            print(f"✅ Task ID: {task_id}")
            
            # 等待结果
            print(f"   等待处理...", end=" ")
            result_data = self.wait_for_result(task_id)
            print(f"\n   ✅ 完成！识别 {len(result_data.get('result', []))} 个片段")
            
            # 格式化并保存
            output_text = self.format_result(result_data)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output_text)
            
            print(f"   💾 保存: {output_file}")
            
            # 记录已处理
            self.processed_files[file_id] = {
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "output": str(output_file),
            }
            self._save_processed()
            
            self.processed_count += 1
            return True
            
        except Exception as e:
            print(f"\n   ❌ 失败: {e}")
            self.failed_count += 1
            return False
    
    def run(self, max_files: int = None):
        """运行批量处理"""
        # 获取所有 MP3 文件
        mp3_files = self.get_all_mp3_files()
        total = len(mp3_files)
        
        # 过滤掉已处理的文件
        pending_files = [f for f in mp3_files 
                        if str(f.relative_to(self.input_dir)) not in self.processed_files]
        pending_count = len(pending_files)
        
        print(f"🔍 找到 {total} 个 MP3 文件")
        print(f"⏭️  已处理: {total - pending_count} 个，待处理: {pending_count} 个")
        print(f"📂 输入目录: {self.input_dir}")
        print(f"📂 输出目录: {self.output_dir}")
        print(f"🌐 Tunnel URL: {self.tunnel_url}")
        print("=" * 60)
        
        if pending_count == 0:
            print("✅ 所有文件已处理完成！")
            return
        
        if max_files:
            pending_files = pending_files[:max_files]
            print(f"⚠️  仅处理前 {max_files} 个待处理文件")
        
        # 处理每个文件
        for i, mp3_file in enumerate(pending_files, 1):
            print(f"\n[{i}/{len(pending_files)}] ", end="")
            self.process_file(mp3_file)
            
            # 每处理完一个文件，等待一下避免 API 限流
            if i < len(pending_files):
                time.sleep(2)
        
        # 最终统计
        print("\n" + "=" * 60)
        print("📊 处理完成统计:")
        print(f"   ✅ 成功: {self.processed_count}")
        print(f"   ⏭️  跳过: {self.skip_count}")
        print(f"   ❌ 失败: {self.failed_count}")
        print(f"   📁 总计: {self.processed_count + self.skip_count + self.failed_count}")


def main():
    parser = argparse.ArgumentParser(
        description="批量音频转文本工具 (STT)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s https://xxx.trycloudflare.com
  %(prog)s https://xxx.trycloudflare.com --max-files 5
  %(prog)s https://xxx.trycloudflare.com --input 00_audio_splits --output 01_stt
        """,
    )
    
    parser.add_argument(
        "tunnel_url",
        help="Cloudflare Tunnel 公网 URL"
    )
    parser.add_argument(
        "--input",
        default="00_audio_splits",
        help="输入目录 (默认: 00_audio_splits)"
    )
    parser.add_argument(
        "--output",
        default="01_stt",
        help="输出目录 (默认: 01_stt)"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多处理文件数（用于测试）"
    )
    
    args = parser.parse_args()
    
    # 创建处理器
    processor = BatchSTTProcessor(
        input_dir=args.input,
        output_dir=args.output,
        tunnel_url=args.tunnel_url
    )
    
    # 运行处理
    processor.run(max_files=args.max_files)


if __name__ == "__main__":
    main()
