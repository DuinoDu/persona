#!/usr/bin/env python3
"""
语音转文本工具 (TTS - Speech to Text with Speaker Recognition)
使用 RecCloud API 实现语音转文字并区分说话人

API 文档:
- 创建任务: https://reccloud.cn/speech-to-text-speaker-create-api-doc
- 查询任务: https://reccloud.cn/speech-to-text-speaker-query-api-doc
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests


# API 配置
API_TOKEN = "wx9x920cn51c8t1ye"
CREATE_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition"
QUERY_API_URL = "https://techsz.aoscdn.com/api/tasks/audio/recognition/{task_id}"


class SpeechToText:
    """语音转文本客户端"""

    def __init__(self, token: str = API_TOKEN):
        self.token = token
        self.headers = {
            "X-API-Key": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def create_task(
        self,
        url: str,
        language: Optional[str] = None,
        speaker_recognition: bool = True,
    ) -> dict:
        """
        创建语音识别任务

        Args:
            url: 音频文件 URL
            language: 输出语言，如 'zh', 'en'，默认自动检测
            speaker_recognition: 是否识别说话人

        Returns:
            API 响应数据
        """
        # 从 URL 提取扩展名
        parsed = urlparse(url)
        path = parsed.path
        extension = Path(path).suffix.lstrip(".") if "." in path else None

        payload = {
            "url": url,
            "type": 4,  # 区分说话人模式
            "speaker_recognition": 1 if speaker_recognition else 0,
        }

        if extension:
            payload["extension"] = extension

        if language:
            payload["language"] = language

        print(f"🎙️  创建语音识别任务...")
        print(f"   URL: {url}")
        print(f"   语言: {language or '自动检测'}")
        print(f"   说话人识别: {'开启' if speaker_recognition else '关闭'}")

        try:
            response = requests.post(
                CREATE_API_URL,
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != 200:
                raise Exception(f"API 错误: {data.get('message', '未知错误')}")

            task_id = data["data"]["task_id"]
            print(f"✅ 任务创建成功，Task ID: {task_id}")
            return data["data"]

        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")

    def query_task(self, task_id: str) -> dict:
        """
        查询任务状态和结果

        Args:
            task_id: 任务 ID

        Returns:
            API 响应数据
        """
        url = QUERY_API_URL.format(task_id=task_id)

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != 200:
                raise Exception(f"API 错误: {data.get('message', '未知错误')}")

            return data["data"]

        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")

    def wait_for_result(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_retries: int = 120,
    ) -> dict:
        """
        等待任务完成并获取结果

        Args:
            task_id: 任务 ID
            poll_interval: 轮询间隔（秒）
            max_retries: 最大重试次数

        Returns:
            任务结果
        """
        print(f"⏳ 等待处理完成...")

        for i in range(max_retries):
            data = self.query_task(task_id)
            state = data.get("state")
            progress = data.get("progress", 0)
            state_detail = data.get("state_detail", "")

            # 更新进度
            if i == 0 or (i + 1) % 12 == 0:  # 每 60 秒或首次打印
                print(f"   状态: {state_detail} | 进度: {progress}%")

            # 任务完成
            if state == 1:
                print(f"✅ 处理完成！")
                return data

            # 任务失败
            if state < 0:
                raise Exception(f"任务失败: {state_detail}")

            # 还在处理中
            time.sleep(poll_interval)

        raise Exception("等待超时，请稍后手动查询")

    def format_result(self, data: dict, output_format: str = "text") -> str:
        """
        格式化识别结果

        Args:
            data: API 返回的数据
            output_format: 输出格式 (text, json, srt)

        Returns:
            格式化后的字符串
        """
        result = data.get("result", [])
        source_language = data.get("source_language", "unknown")
        duration = data.get("duration", 0)

        if output_format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)

        if output_format == "srt":
            return self._format_srt(result)

        # 默认文本格式，带说话人区分
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

            # 转换时间为可读格式
            start_time = self._ms_to_time(start_ms)
            end_time = self._ms_to_time(end_ms)

            # 说话人变化时添加分隔
            if speaker != current_speaker:
                lines.append(f"\n[{speaker}] {start_time} - {end_time}")
                current_speaker = speaker
            else:
                lines.append(f"[{start_time} - {end_time}]")

            lines.append(f"{text}\n")

        return "\n".join(lines)

    def _format_srt(self, result: list) -> str:
        """格式化为 SRT 字幕格式"""
        lines = []
        for i, item in enumerate(result, 1):
            start_ms = item.get("start", 0)
            end_ms = item.get("end", 0)
            text = item.get("text", "").strip()
            speaker = item.get("speaker", "未知")

            start_srt = self._ms_to_srt_time(start_ms)
            end_srt = self._ms_to_srt_time(end_ms)

            lines.append(str(i))
            lines.append(f"{start_srt} --> {end_srt}")
            lines.append(f"[{speaker}] {text}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _ms_to_time(ms: int) -> str:
        """毫秒转换为 HH:MM:SS 格式"""
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _ms_to_srt_time(ms: int) -> str:
        """毫秒转换为 SRT 时间格式 HH:MM:SS,mmm"""
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        millis = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    parser = argparse.ArgumentParser(
        description="语音转文本工具 (支持说话人识别)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://example.com/audio.mp3"
  %(prog)s "https://example.com/audio.mp3" -l zh
  %(prog)s "https://example.com/audio.mp3" -o result.txt
  %(prog)s "https://example.com/audio.mp3" -f json -o result.json
  %(prog)s "https://example.com/audio.mp3" -f srt -o result.srt
        """,
    )

    parser.add_argument("url", help="音频文件的 URL 地址")
    parser.add_argument(
        "-l", "--language",
        default="zh",
        help="输出语言 (如: zh, en, ja, ko)，默认自动检测"
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
        "--poll-interval",
        type=int,
        default=5,
        help="轮询间隔秒数 (默认: 5)"
    )
    parser.add_argument(
        "--token",
        default=API_TOKEN,
        help=f"API Token (默认: {API_TOKEN[:8]}...)"
    )

    args = parser.parse_args()

    # 初始化客户端
    client = SpeechToText(token=args.token)

    try:
        # 创建任务
        task_data = client.create_task(
            url=args.url,
            language=args.language,
            speaker_recognition=not args.no_speaker,
        )
        task_id = task_data["task_id"]

        # 等待结果
        result_data = client.wait_for_result(
            task_id=task_id,
            poll_interval=args.poll_interval,
        )

        # 格式化输出
        output = client.format_result(result_data, output_format=args.format)

        # 保存或输出
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
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
