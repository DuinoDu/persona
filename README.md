# QuQu YouTube Live Stream Processing Pipeline

YouTube 频道 @QuQuUP 直播内容处理流水线：从视频下载到对话语料提取。

## 目录结构

```
.
├── Makefile                    # 流水线入口，make help 查看命令
├── packages/
│   ├── player/                 # Web frontend / admin console
│   └── agent/                  # Persona harness / LLM runner / H20 orchestration
├── scripts/                    # 流水线脚本（按步骤编号）
│   ├── 01_download_audio.sh    # Step 1: YouTube 播放列表下载 MP3
│   ├── 02_split_audio.py       # Step 2: 长音频按 2 小时分割
│   ├── 03_batch_transcribe.sh  # Step 3: 批量语音转文字
│   ├── 03_split_transcribe_merge.py  # Step 3 辅助: 单文件分片转写+合并
│   ├── 04_merge_transcripts.py # Step 4: 合并 part JSON 按日期
│   ├── 05_extract_conversations.py # Step 5: 提取观众连麦对话
│   ├── serve_mp3.sh            # 工具: HTTP + Cloudflare Tunnel 服务
│   └── evals/                  # 兼容入口；真实实现已迁到 packages/agent/scripts/evals
├── speech2text/                # 本地语音转文字引擎 (Whisper + pyannote)
├── data/                       # 数据目录（git 忽略）
│   ├── 01_downloads/           # 原始 MP3 下载
│   ├── 02_audio_splits/        # 分割后的音频 + 分片转写 JSON
│   ├── 03_transcripts/         # 合并后的完整转写 JSON
│   └── 04_conversations/       # 最终对话语料
├── deprecated/                 # 已弃用的旧脚本
└── docs/                       # 文档和笔记
```

## 数据流

```
data/01_downloads/          (yt-dlp 下载的 MP3)
       │  Step 2: 02_split_audio.py
       ▼
data/02_audio_splits/       (≤2h 的 MP3 分片)
       │  Step 3: 03_batch_transcribe.sh (Whisper + 说话人分离)
       ▼
data/02_audio_splits/*.json (分片转写 JSON，含 speaker + timestamp)
       │  Step 4: 04_merge_transcripts.py
       ▼
data/03_transcripts/        (按日期合并的完整转写 JSON)
       │  Step 5: 05_extract_conversations.py
       ▼
data/04_conversations/      (按日期/观众分割的对话语料)
```

## 快速开始

```bash
# 查看帮助
make help

# 查看当前各阶段数据量
make status

# 运行完整流水线（不含下载）
make pipeline

# 单步运行
make step1-download     # 下载音频
make step2-split        # 分割音频
make step3-transcribe   # 语音转文字
make step4-merge        # 合并转写结果
make step5-extract      # 提取对话
```

## 技术栈

- **包管理**: uv + pyproject.toml
- **视频下载**: yt-dlp
- **音频处理**: ffmpeg / ffprobe
- **语音识别**: Whisper (faster-whisper) + pyannote (说话人分离)
- **网络穿透**: Cloudflare Tunnel

## Package 边界

- `packages/player`: 前端、后台控制台、API routes、Prisma schema
- `packages/agent`: persona harness、LLM runner、H20 orchestration、trace/export domain logic

Web 控制面与管理后台位于 `packages/player/`；persona harness、评测编排与 H20 orchestration 位于 `packages/agent/`。

## 输出格式

每个对话文件 (data/04_conversations/YYYYMMDD/日期_开始_结束_标签.json):

```json
{
  "conversation_id": 1,
  "start_time": 707.63,
  "end_time": 2597.85,
  "guest_tag": "39岁医学博士",
  "host_speaker": "SPEAKER_02",
  "guest_speaker": "SPEAKER_00",
  "segments": [
    {"start": 707.63, "end": 720.5, "speaker": "SPEAKER_00", "text": "..."},
    ...
  ]
}
```
