# 中文双人对话语音转文本工具

基于 Whisper + pyannote 的本地语音转文本工具，专为中文双人对话/访谈场景设计。

## 功能特点

- **中文优化**: 使用 Whisper large-v3 模型，强制指定中文语言
- **说话人分离**: 基于 pyannote-audio 自动区分两位说话人
- **多种输出格式**: 支持纯文本、SRT 字幕、JSON 格式
- **4090 优化**: 针对 RTX 4090 配置，使用 float16 精度和较大 batch_size

## 环境要求

- Python >= 3.12
- NVIDIA GPU (推荐 RTX 4090)
- CUDA 12.1+
- HuggingFace 账号和 Token

## 安装

### 1. 获取 HuggingFace Token

1. 访问 https://huggingface.co/settings/tokens 创建 Access Token
2. 访问以下页面并同意使用条款：
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0

### 2. 安装依赖

```bash
cd speech2text

# 使用 uv 安装依赖
uv sync

# 设置 HuggingFace Token
export HF_TOKEN="your_token_here"
```

## 使用方法

### 基本用法

```bash
# 转录音频文件
uv run transcribe interview.mp3

# 或者激活虚拟环境后直接运行
source .venv/bin/activate
transcribe interview.mp3
```

### 指定输出格式

```bash
# 输出 SRT 字幕
uv run transcribe interview.mp3 -f srt

# 输出 JSON
uv run transcribe interview.mp3 -f json

# 输出所有格式
uv run transcribe interview.mp3 -f all
```

### 自定义说话人名称

```bash
uv run transcribe interview.mp3 -s "主持人,嘉宾"
```

### 指定输出路径

```bash
uv run transcribe interview.mp3 -o ./output/result.txt
uv run transcribe interview.mp3 -f all -o ./output/
```

### 完整参数

```
用法: transcribe [OPTIONS] AUDIO_FILE

选项:
  -f, --format [text|srt|json|all]  输出格式 (默认: text)
  -o, --output PATH                  输出文件路径
  -s, --speakers TEXT                说话人名称，逗号分隔 (例如: '主持人,嘉宾')
  -m, --model [large-v3|large-v2|medium|small]
                                     Whisper 模型大小 (默认: large-v3)
  -d, --device TEXT                  计算设备 (默认: cuda)
  -b, --batch-size INTEGER           批处理大小 (默认: 16)
  -n, --num-speakers INTEGER         说话人数量 (默认: 2)
  --hf-token TEXT                    HuggingFace Token
  --help                             显示帮助信息
```

## 输出示例

### 纯文本格式 (.txt)

```
[00:00:01 - 00:00:05] 主持人: 欢迎来到今天的节目，我们来聊一下人工智能
[00:00:06 - 00:00:12] 嘉宾: 谢谢邀请，这个话题我非常感兴趣
[00:00:13 - 00:00:18] 主持人: 你认为大模型未来会如何发展？
```

### SRT 字幕格式 (.srt)

```
1
00:00:01,000 --> 00:00:05,000
[主持人] 欢迎来到今天的节目，我们来聊一下人工智能

2
00:00:06,000 --> 00:00:12,000
[嘉宾] 谢谢邀请，这个话题我非常感兴趣
```

### JSON 格式 (.json)

```json
{
  "segments": [
    {
      "start": 1.0,
      "end": 5.0,
      "speaker": "主持人",
      "text": "欢迎来到今天的节目，我们来聊一下人工智能"
    }
  ],
  "speakers": ["主持人", "嘉宾"]
}
```

## 支持的音频格式

MP3, WAV, M4A, FLAC, OGG, WMA 等常见音频格式

## 性能参考 (RTX 4090)

| 音频时长 | 处理时间 (约) |
|----------|---------------|
| 10 分钟  | 1-2 分钟      |
| 30 分钟  | 3-5 分钟      |
| 60 分钟  | 6-10 分钟     |

## 注意事项

1. **首次运行会下载模型**: large-v3 约 3GB，pyannote 模型约 500MB
2. **HuggingFace Token 必须配置**: 否则 pyannote 模型无法下载
3. **长音频建议**: 超过 1 小时的音频建议分段处理
4. **显存占用**: 峰值约 10GB，4090 完全足够
