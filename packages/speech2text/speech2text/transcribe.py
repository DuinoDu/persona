"""
中文双人对话语音转文本工具

使用 faster-whisper + pyannote.audio 实现：
- 中文语音识别
- 说话人分离（双人对话）
- 多种输出格式
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import torch
import numpy as np
from huggingface_hub import login as hf_login
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def format_timestamp(seconds: float) -> str:
    """将秒数转换为 HH:MM:SS 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_srt_timestamp(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def load_audio(file_path: str, sr: int = 16000, channels: int = 1) -> np.ndarray:
    """加载音频文件"""
    import subprocess

    cmd = [
        "ffmpeg", "-i", file_path,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-ac", str(channels),
        "-"
    ]

    process = subprocess.run(cmd, capture_output=True)
    audio = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def preprocess_to_wav(
    audio_path: str,
    output_path: str,
    sr: int = 16000,
    channels: int = 1,
    denoise: bool = True,
    highpass_hz: float = 80.0,
    loudnorm: bool = True,
) -> str:
    """音频预处理：降噪 + 高通 + 响度归一化"""
    import subprocess

    filters = []
    if highpass_hz and highpass_hz > 0:
        filters.append(f"highpass=f={highpass_hz}")
    if denoise:
        filters.append("afftdn")
    if loudnorm:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ar", str(sr),
        "-ac", str(channels),
        "-c:a", "pcm_s16le",
    ]
    if filters:
        cmd.extend(["-af", ",".join(filters)])
    cmd.append(output_path)

    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def load_models(
    model_size: str = "large-v3",
    device: str = "cuda",
    compute_type: str = "float16",
    hf_token: Optional[str] = None,
):
    """加载 Whisper 和 pyannote 模型"""

    # 先全局登录 HuggingFace，确保嵌套模型下载也能使用 token
    if hf_token:
        hf_login(token=hf_token, add_to_git_credential=False)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # 加载 Whisper 模型
        progress.add_task(description="加载 Whisper 模型...", total=None)
        whisper_model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

        # 加载说话人分离模型
        progress.add_task(description="加载说话人分离模型...", total=None)
        diarize_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
        if device == "cuda":
            diarize_pipeline.to(torch.device("cuda"))

    return whisper_model, diarize_pipeline


def load_embedding_inference(
    embedding_model: str,
    device: str,
    hf_token: Optional[str] = None,
):
    """加载说话人嵌入模型"""
    from pyannote.audio import Inference, Model

    model = Model.from_pretrained(embedding_model, use_auth_token=hf_token)
    try:
        inference = Inference(model, window="whole", device=device)
    except TypeError:
        inference = Inference(model, window="whole")
        if hasattr(inference, "to"):
            inference.to(torch.device(device))

    return inference


def transcribe_with_whisper(
    audio: np.ndarray,
    whisper_model: WhisperModel,
    batch_size: int = 16,
    sample_rate: int = 16000,
) -> list:
    """使用 Whisper 转录音频"""
    # 计算音频总时长（秒）
    total_duration = len(audio) / sample_rate

    segments, info = whisper_model.transcribe(
        audio,
        language="zh",
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    result = []
    last_progress = 0

    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

        # 计算并打印进度（每10%更新一次）
        if total_duration > 0:
            current_progress = int((seg.end / total_duration) * 100)
            # 每10%打印一次
            if current_progress >= last_progress + 10:
                last_progress = (current_progress // 10) * 10
                console.print(f"  [cyan]转录进度: {last_progress}%[/cyan]")

    return result


def convert_to_wav(
    audio_path: str,
    output_path: str,
    sr: int = 16000,
    channels: int = 1,
) -> str:
    """将音频转换为标准 WAV 格式，解决 pyannote 采样数不匹配问题"""
    import subprocess

    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ar", str(sr),
        "-ac", str(channels),
        "-c:a", "pcm_s16le",
        output_path
    ]

    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def get_wav_duration(wav_path: str) -> float:
    """获取 WAV 音频时长（秒）"""
    import contextlib
    import wave

    with contextlib.closing(wave.open(wav_path, "rb")) as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    return frames / float(rate) if rate else 0.0


def extract_wav_segment(
    wav_path: str,
    start: float,
    duration: float,
    output_path: str,
) -> str:
    """从 WAV 中切片，生成新的 WAV 文件"""
    import subprocess

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", wav_path,
        "-c:a", "pcm_s16le",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def run_diarization(
    diarize_pipeline: Pipeline,
    wav_path: str,
    num_speakers: Optional[int],
    min_speakers: Optional[int],
    max_speakers: Optional[int],
    auto_speakers: bool,
):
    """执行 pyannote 说话人分离"""
    kwargs = {}
    if auto_speakers:
        kwargs = {}
    elif min_speakers is not None or max_speakers is not None:
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers
    elif num_speakers is not None:
        kwargs["min_speakers"] = num_speakers
        kwargs["max_speakers"] = num_speakers

    return diarize_pipeline(wav_path, **kwargs)


def collect_diarization_segments(result) -> List[dict]:
    """统一 pyannote 输出格式"""
    if hasattr(result, "speaker_diarization"):
        diarization = result.speaker_diarization
    else:
        diarization = result

    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker,
        })
    return segments


def compute_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """计算两个时间区间的重叠长度"""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算余弦相似度"""
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


def compute_speaker_embeddings(
    wav_path: str,
    segments: List[dict],
    inference,
    min_duration: float = 1.0,
) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    """计算每个 speaker 的嵌入向量（按时长加权平均）"""
    embeddings: Dict[str, np.ndarray] = {}
    durations: Dict[str, float] = {}

    for seg in segments:
        duration = max(0.0, seg["end"] - seg["start"])
        if duration < min_duration:
            continue

        try:
            emb = inference({
                "audio": wav_path,
                "start": float(seg["start"]),
                "end": float(seg["end"]),
            })
        except Exception:
            continue

        emb = np.asarray(emb).squeeze()
        if emb.ndim != 1:
            emb = emb.reshape(-1)

        speaker = seg["speaker"]
        if speaker not in embeddings:
            embeddings[speaker] = emb * duration
            durations[speaker] = duration
        else:
            embeddings[speaker] += emb * duration
            durations[speaker] += duration

    for speaker, total in list(durations.items()):
        if total <= 0:
            embeddings.pop(speaker, None)
            durations.pop(speaker, None)
            continue
        embeddings[speaker] = embeddings[speaker] / total

    return embeddings, durations


def apply_embedding_alignment(
    mapping: Dict[str, str],
    local_embeddings: Dict[str, np.ndarray],
    global_profiles: Dict[str, Dict[str, np.ndarray]],
    similarity_threshold: float,
) -> Dict[str, str]:
    """使用嵌入相似度对齐未匹配的 speaker"""
    if not local_embeddings or not global_profiles:
        return mapping

    used_globals = set(mapping.values())
    for local_spk, local_emb in local_embeddings.items():
        if local_spk in mapping:
            continue

        best_score = -1.0
        best_global = None
        for global_spk, profile in global_profiles.items():
            if global_spk in used_globals:
                continue
            score = cosine_similarity(local_emb, profile["embedding"])
            if score > best_score:
                best_score = score
                best_global = global_spk

        if best_global is not None and best_score >= similarity_threshold:
            mapping[local_spk] = best_global
            used_globals.add(best_global)

    return mapping


def update_global_profiles(
    global_profiles: Dict[str, Dict[str, np.ndarray]],
    mapping: Dict[str, str],
    local_embeddings: Dict[str, np.ndarray],
    local_durations: Dict[str, float],
):
    """更新跨段 speaker 嵌入档案"""
    for local_spk, global_spk in mapping.items():
        if local_spk not in local_embeddings:
            continue
        emb = local_embeddings[local_spk]
        duration = local_durations.get(local_spk, 0.0)
        if duration <= 0:
            continue

        if global_spk not in global_profiles:
            global_profiles[global_spk] = {
                "embedding": emb,
                "duration": duration,
            }
            continue

        prev = global_profiles[global_spk]
        total = prev["duration"] + duration
        prev["embedding"] = (prev["embedding"] * prev["duration"] + emb * duration) / total
        prev["duration"] = total


def map_local_speakers_to_global(
    local_segments: List[dict],
    global_segments: List[dict],
    overlap_start: float,
    overlap_end: float,
    next_speaker_index: int,
) -> Tuple[Dict[str, str], int]:
    """根据重叠区间对齐跨段 speaker label"""
    local_speakers = sorted({s["speaker"] for s in local_segments})
    global_speakers = sorted({s["speaker"] for s in global_segments})

    if not global_segments or overlap_end <= overlap_start:
        mapping = {}
        for speaker in local_speakers:
            mapping[speaker] = f"SPEAKER_{next_speaker_index:02d}"
            next_speaker_index += 1
        return mapping, next_speaker_index

    overlap_scores: List[Tuple[float, str, str]] = []
    for local in local_segments:
        local_overlap = compute_overlap(local["start"], local["end"], overlap_start, overlap_end)
        if local_overlap <= 0:
            continue
        for global_seg in global_segments:
            global_overlap = compute_overlap(global_seg["start"], global_seg["end"], overlap_start, overlap_end)
            if global_overlap <= 0:
                continue
            overlap = compute_overlap(
                local["start"],
                local["end"],
                global_seg["start"],
                global_seg["end"],
            )
            if overlap > 0:
                overlap_scores.append((overlap, local["speaker"], global_seg["speaker"]))

    overlap_scores.sort(reverse=True)
    mapping: Dict[str, str] = {}
    used_global = set()
    for score, local_spk, global_spk in overlap_scores:
        if local_spk in mapping or global_spk in used_global or score <= 0:
            continue
        mapping[local_spk] = global_spk
        used_global.add(global_spk)

    for speaker in local_speakers:
        if speaker not in mapping:
            mapping[speaker] = f"SPEAKER_{next_speaker_index:02d}"
            next_speaker_index += 1

    return mapping, next_speaker_index


def diarize_audio(
    audio_path: str,
    diarize_pipeline: Pipeline,
    num_speakers: Optional[int] = 2,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    auto_speakers: bool = False,
    chunk_seconds: Optional[float] = None,
    overlap_seconds: float = 0.0,
    diarize_stereo: bool = False,
    prepared_wav_path: Optional[str] = None,
    embedding_inference=None,
    embedding_align: bool = False,
    embedding_min_duration: float = 1.0,
    embedding_similarity_threshold: float = 0.65,
) -> list:
    """使用 pyannote 进行说话人分离"""
    import tempfile

    # 先转换为标准 WAV 格式，避免采样数不匹配问题
    cleanup_tmp = False
    if prepared_wav_path:
        tmp_wav = prepared_wav_path
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
        cleanup_tmp = True

    try:
        if not prepared_wav_path:
            channels = 2 if diarize_stereo else 1
            convert_to_wav(audio_path, tmp_wav, channels=channels)

        if not chunk_seconds or chunk_seconds <= 0:
            result = run_diarization(
                diarize_pipeline,
                tmp_wav,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                auto_speakers=auto_speakers,
            )
            return collect_diarization_segments(result)

        duration = get_wav_duration(tmp_wav)
        if duration <= 0:
            return []

        if overlap_seconds >= chunk_seconds:
            overlap_seconds = max(0.0, chunk_seconds * 0.1)

        chunk_start = 0.0
        next_speaker_index = 0
        global_segments: List[dict] = []
        global_profiles: Dict[str, Dict[str, np.ndarray]] = {}
        prev_chunk_end = 0.0

        while chunk_start < duration:
            chunk_end = min(duration, chunk_start + chunk_seconds)
            chunk_duration = max(0.0, chunk_end - chunk_start)
            if chunk_duration <= 0:
                break

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as chunk_tmp:
                chunk_wav = chunk_tmp.name

            try:
                extract_wav_segment(tmp_wav, chunk_start, chunk_duration, chunk_wav)
                chunk_result = run_diarization(
                    diarize_pipeline,
                    chunk_wav,
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                    auto_speakers=auto_speakers,
                )
                local_segments = collect_diarization_segments(chunk_result)
            finally:
                if os.path.exists(chunk_wav):
                    os.remove(chunk_wav)

            for seg in local_segments:
                seg["start"] += chunk_start
                seg["end"] += chunk_start

            local_embeddings: Dict[str, np.ndarray] = {}
            local_durations: Dict[str, float] = {}
            if embedding_align and embedding_inference is not None:
                local_embeddings, local_durations = compute_speaker_embeddings(
                    tmp_wav,
                    local_segments,
                    embedding_inference,
                    min_duration=embedding_min_duration,
                )

            overlap_start = chunk_start
            overlap_end = min(chunk_start + overlap_seconds, prev_chunk_end)
            mapping, next_speaker_index = map_local_speakers_to_global(
                local_segments,
                global_segments,
                overlap_start,
                overlap_end,
                next_speaker_index,
            )
            if embedding_align:
                mapping = apply_embedding_alignment(
                    mapping,
                    local_embeddings,
                    global_profiles,
                    similarity_threshold=embedding_similarity_threshold,
                )

            mapped_segments = []
            for seg in local_segments:
                mapped = seg.copy()
                mapped["speaker"] = mapping.get(seg["speaker"], seg["speaker"])
                mapped_segments.append(mapped)

            if embedding_align:
                update_global_profiles(
                    global_profiles,
                    mapping,
                    local_embeddings,
                    local_durations,
                )

            overlap_cutoff = chunk_start + overlap_seconds if chunk_start > 0 else chunk_start
            for seg in mapped_segments:
                if chunk_start > 0:
                    if seg["end"] <= overlap_cutoff:
                        continue
                    if seg["start"] < overlap_cutoff:
                        seg["start"] = overlap_cutoff
                global_segments.append(seg)

            prev_chunk_end = chunk_end
            chunk_start = chunk_start + chunk_seconds - overlap_seconds
            if chunk_start <= 0:
                chunk_start = chunk_end
    finally:
        # 清理临时文件
        if cleanup_tmp and os.path.exists(tmp_wav):
            os.remove(tmp_wav)

    return sorted(global_segments, key=lambda seg: seg["start"])


def assign_speakers(
    transcription: list,
    diarization: list,
) -> list:
    """将说话人信息分配给转录片段"""

    for trans_seg in transcription:
        trans_start = trans_seg["start"]
        trans_end = trans_seg["end"]
        trans_mid = (trans_start + trans_end) / 2

        # 找到与转录片段重叠最多的说话人
        best_speaker = "UNKNOWN"
        best_overlap = 0

        for diar_seg in diarization:
            diar_start = diar_seg["start"]
            diar_end = diar_seg["end"]

            # 计算重叠
            overlap_start = max(trans_start, diar_start)
            overlap_end = min(trans_end, diar_end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar_seg["speaker"]

        # 如果没有重叠，使用中点所在的说话人
        if best_speaker == "UNKNOWN":
            for diar_seg in diarization:
                if diar_seg["start"] <= trans_mid <= diar_seg["end"]:
                    best_speaker = diar_seg["speaker"]
                    break

        trans_seg["speaker"] = best_speaker

    return transcription


def split_transcription_by_diarization(
    transcription: list,
    diarization: list,
) -> list:
    """在 diarization 边界拆分转录片段，并分配 speaker"""
    diarization_sorted = sorted(diarization, key=lambda seg: seg["start"])
    output_segments = []

    for trans_seg in transcription:
        trans_start = trans_seg["start"]
        trans_end = trans_seg["end"]
        text = trans_seg["text"].strip()

        overlaps = []
        for diar_seg in diarization_sorted:
            overlap = compute_overlap(trans_start, trans_end, diar_seg["start"], diar_seg["end"])
            if overlap > 0:
                overlaps.append((diar_seg, overlap))

        if not overlaps:
            output_segments.append({
                "start": trans_start,
                "end": trans_end,
                "text": text,
                "speaker": "UNKNOWN",
            })
            continue

        if len(overlaps) == 1:
            diar_seg = overlaps[0][0]
            output_segments.append({
                "start": max(trans_start, diar_seg["start"]),
                "end": min(trans_end, diar_seg["end"]),
                "text": text,
                "speaker": diar_seg["speaker"],
            })
            continue

        overlaps.sort(key=lambda item: item[0]["start"])
        total_overlap = sum(item[1] for item in overlaps)
        if total_overlap <= 0:
            output_segments.append({
                "start": trans_start,
                "end": trans_end,
                "text": text,
                "speaker": "UNKNOWN",
            })
            continue

        text_len = len(text)
        if text_len == 0:
            for diar_seg, _ in overlaps:
                output_segments.append({
                    "start": max(trans_start, diar_seg["start"]),
                    "end": min(trans_end, diar_seg["end"]),
                    "text": "",
                    "speaker": diar_seg["speaker"],
                })
            continue

        raw_counts = [item[1] / total_overlap * text_len for item in overlaps]
        base_counts = [int(count) for count in raw_counts]
        remainder = text_len - sum(base_counts)
        fractional = [(raw_counts[i] - base_counts[i], i) for i in range(len(base_counts))]
        fractional.sort(reverse=True)
        for _, idx in fractional[:remainder]:
            base_counts[idx] += 1

        cursor = 0
        for (diar_seg, _), count in zip(overlaps, base_counts):
            piece = text[cursor:cursor + count].strip()
            cursor += count
            output_segments.append({
                "start": max(trans_start, diar_seg["start"]),
                "end": min(trans_end, diar_seg["end"]),
                "text": piece,
                "speaker": diar_seg["speaker"],
            })

    return output_segments


def compute_speaker_durations(segments: list) -> Dict[str, float]:
    """统计每个 speaker 的总时长"""
    durations: Dict[str, float] = {}
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        if speaker == "UNKNOWN":
            continue
        durations[speaker] = durations.get(speaker, 0.0) + max(0.0, seg["end"] - seg["start"])
    return durations


def build_speaker_name_map(
    speaker_names: Optional[List[str]],
    segments: list,
    auto_map: bool,
) -> Optional[Dict[str, str]]:
    """根据时长稳定映射 speaker 名称"""
    if not speaker_names:
        return None

    if not auto_map:
        return {f"SPEAKER_{i:02d}": name for i, name in enumerate(speaker_names)}

    durations = compute_speaker_durations(segments)
    sorted_speakers = sorted(durations.items(), key=lambda item: item[1], reverse=True)
    mapping: Dict[str, str] = {}
    for idx, (speaker, _) in enumerate(sorted_speakers):
        if idx < len(speaker_names):
            mapping[speaker] = speaker_names[idx]

    return mapping if mapping else None


def transcribe_audio(
    audio_path: str,
    whisper_model: WhisperModel,
    diarize_pipeline: Pipeline,
    num_speakers: Optional[int] = 2,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    auto_speakers: bool = False,
    chunk_seconds: Optional[float] = None,
    overlap_seconds: float = 0.0,
    diarize_stereo: bool = False,
    split_by_diarization: bool = True,
    preprocess: bool = False,
    denoise: bool = True,
    highpass_hz: float = 80.0,
    loudnorm: bool = True,
    embedding_inference=None,
    embedding_align: bool = False,
    embedding_min_duration: float = 1.0,
    embedding_similarity_threshold: float = 0.65,
    batch_size: int = 16,
):
    """转录音频并进行说话人分离"""

    import tempfile

    prepared_wav_path = None
    try:
        # 加载音频
        console.print("  [dim]加载音频文件...[/dim]")
        if preprocess:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                prepared_wav_path = tmp.name

            channels = 2 if diarize_stereo else 1
            preprocess_to_wav(
                audio_path,
                prepared_wav_path,
                sr=16000,
                channels=channels,
                denoise=denoise,
                highpass_hz=highpass_hz,
                loudnorm=loudnorm,
            )
            audio = load_audio(prepared_wav_path)
        else:
            audio = load_audio(audio_path)

        audio_duration = len(audio) / 16000
        console.print(f"  [dim]音频时长: {audio_duration:.1f} 秒[/dim]")

        # Whisper 转录
        console.print("  [dim]开始转录...[/dim]")
        transcription = transcribe_with_whisper(audio, whisper_model, batch_size, sample_rate=16000)
        console.print("  [cyan]转录进度: 100%[/cyan]")

        # 说话人分离
        console.print("  [dim]开始说话人分离...[/dim]")
        diarization = diarize_audio(
            audio_path,
            diarize_pipeline,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            auto_speakers=auto_speakers,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            diarize_stereo=diarize_stereo,
            prepared_wav_path=prepared_wav_path,
            embedding_inference=embedding_inference,
            embedding_align=embedding_align,
            embedding_min_duration=embedding_min_duration,
            embedding_similarity_threshold=embedding_similarity_threshold,
        )
        console.print("  [cyan]说话人分离: 100%[/cyan]")
    finally:
        if prepared_wav_path and os.path.exists(prepared_wav_path):
            os.remove(prepared_wav_path)

    # 合并结果
    console.print("  [dim]合并转录结果...[/dim]")
    if split_by_diarization:
        result = split_transcription_by_diarization(transcription, diarization)
    else:
        result = assign_speakers(transcription, diarization)

    return result


def output_text(
    segments: list,
    speaker_names: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> str:
    """输出纯文本格式"""
    lines = []

    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        speaker = seg.get("speaker", "UNKNOWN")

        if speaker_names and speaker in speaker_names:
            speaker = speaker_names[speaker]

        text = seg["text"].strip()
        lines.append(f"[{start} - {end}] {speaker}: {text}")

    content = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        console.print(f"[green]已保存到: {output_path}[/green]")

    return content


def output_srt(
    segments: list,
    speaker_names: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> str:
    """输出 SRT 字幕格式"""
    lines = []

    for i, seg in enumerate(segments, 1):
        start = format_srt_timestamp(seg["start"])
        end = format_srt_timestamp(seg["end"])
        speaker = seg.get("speaker", "UNKNOWN")

        if speaker_names and speaker in speaker_names:
            speaker = speaker_names[speaker]

        text = seg["text"].strip()

        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(f"[{speaker}] {text}")
        lines.append("")

    content = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        console.print(f"[green]已保存到: {output_path}[/green]")

    return content


def output_json(
    segments: list,
    speaker_names: Optional[dict] = None,
    output_path: Optional[str] = None,
) -> str:
    """输出 JSON 格式"""
    output_segments = []

    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")

        if speaker_names and speaker in speaker_names:
            speaker = speaker_names[speaker]

        output_segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "speaker": speaker,
            "text": seg["text"].strip(),
        })

    data = {
        "segments": output_segments,
        "speakers": list(set(s["speaker"] for s in output_segments)),
    }

    content = json.dumps(data, ensure_ascii=False, indent=2)

    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        console.print(f"[green]已保存到: {output_path}[/green]")

    return content


def display_result(segments: list, speaker_names: Optional[dict] = None):
    """在终端显示转录结果"""
    table = Table(title="转录结果", show_lines=True)
    table.add_column("时间", style="cyan", width=20)
    table.add_column("说话人", style="magenta", width=12)
    table.add_column("内容", style="white")

    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        speaker = seg.get("speaker", "UNKNOWN")

        if speaker_names and speaker in speaker_names:
            speaker = speaker_names[speaker]

        text = seg["text"].strip()
        table.add_row(f"{start} - {end}", speaker, text)

    console.print(table)


@click.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option(
    "--format", "-f",
    type=click.Choice(["text", "srt", "json", "all"]),
    default="text",
    help="输出格式 (默认: text)",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="输出文件路径 (默认: 与输入文件同目录)",
)
@click.option(
    "--speakers", "-s",
    type=str,
    default=None,
    help="说话人名称，用逗号分隔 (例如: '主持人,嘉宾')",
)
@click.option(
    "--model", "-m",
    type=click.Choice(["large-v3", "large-v2", "medium", "small"]),
    default="large-v3",
    help="Whisper 模型大小 (默认: large-v3)",
)
@click.option(
    "--device", "-d",
    type=str,
    default="cuda",
    help="计算设备 (默认: cuda)",
)
@click.option(
    "--batch-size", "-b",
    type=int,
    default=16,
    help="批处理大小 (默认: 16)",
)
@click.option(
    "--hf-token",
    type=str,
    default=None,
    envvar="HF_TOKEN",
    help="HuggingFace Token (也可通过 HF_TOKEN 环境变量设置)",
)
@click.option(
    "--num-speakers", "-n",
    type=click.IntRange(1, None),
    default=2,
    help="说话人数量 (默认: 2)",
)
@click.option(
    "--min-speakers",
    type=click.IntRange(1, None),
    default=None,
    help="说话人最小数量 (可与 --max-speakers 搭配)",
)
@click.option(
    "--max-speakers",
    type=click.IntRange(1, None),
    default=None,
    help="说话人最大数量 (可与 --min-speakers 搭配)",
)
@click.option(
    "--auto-speakers/--no-auto-speakers",
    default=False,
    help="自动估计说话人数 (默认: 否)",
)
@click.option(
    "--diarize-chunk-minutes",
    type=float,
    default=15.0,
    show_default=True,
    help="分段说话人分离的每段长度（分钟），设为 0 禁用",
)
@click.option(
    "--diarize-overlap-seconds",
    type=float,
    default=8.0,
    show_default=True,
    help="分段说话人分离的重叠秒数",
)
@click.option(
    "--diarize-stereo/--diarize-mono",
    default=False,
    help="说话人分离时保留立体声 (默认: 单声道)",
)
@click.option(
    "--split-by-diarization/--no-split-by-diarization",
    default=True,
    help="按 diarization 边界拆分转录片段 (默认: 是)",
)
@click.option(
    "--auto-map-speakers/--no-auto-map-speakers",
    default=True,
    help="按总时长自动映射说话人名称 (默认: 是)",
)
@click.option(
    "--preprocess/--no-preprocess",
    default=False,
    help="启用音频预处理 (降噪/高通/响度归一化) (默认: 否)",
)
@click.option(
    "--denoise/--no-denoise",
    default=True,
    help="启用降噪 (afftdn) (默认: 是)",
)
@click.option(
    "--highpass-hz",
    type=float,
    default=80.0,
    show_default=True,
    help="高通滤波频率 (Hz)",
)
@click.option(
    "--loudnorm/--no-loudnorm",
    default=True,
    help="启用响度归一化 (默认: 是)",
)
@click.option(
    "--embedding-align/--no-embedding-align",
    default=False,
    help="使用说话人嵌入跨段对齐 (默认: 否)",
)
@click.option(
    "--embedding-model",
    type=str,
    default="pyannote/embedding",
    show_default=True,
    help="说话人嵌入模型",
)
@click.option(
    "--embedding-min-duration",
    type=float,
    default=1.0,
    show_default=True,
    help="计算嵌入时的最小时长 (秒)",
)
@click.option(
    "--embedding-similarity-threshold",
    type=float,
    default=0.65,
    show_default=True,
    help="嵌入相似度阈值 (余弦)",
)
def main(
    audio_file: str,
    format: str,
    output: Optional[str],
    speakers: Optional[str],
    model: str,
    device: str,
    batch_size: int,
    hf_token: Optional[str],
    num_speakers: int,
    min_speakers: Optional[int],
    max_speakers: Optional[int],
    auto_speakers: bool,
    diarize_chunk_minutes: float,
    diarize_overlap_seconds: float,
    diarize_stereo: bool,
    split_by_diarization: bool,
    auto_map_speakers: bool,
    preprocess: bool,
    denoise: bool,
    highpass_hz: float,
    loudnorm: bool,
    embedding_align: bool,
    embedding_model: str,
    embedding_min_duration: float,
    embedding_similarity_threshold: float,
):
    """
    中文双人对话语音转文本工具

    示例:

        transcribe interview.mp3

        transcribe interview.mp3 -f srt -s "主持人,嘉宾"

        transcribe interview.mp3 -f all -o ./output/
    """

    console.print("[bold blue]中文双人对话语音转文本工具[/bold blue]\n")

    # 检查 HuggingFace Token
    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

    if not hf_token:
        console.print(
            "[yellow]警告: 未设置 HuggingFace Token，说话人分离功能可能无法使用。\n"
            "请通过 --hf-token 参数或 HF_TOKEN 环境变量设置。[/yellow]\n"
        )

    # 解析说话人名称
    speaker_list = None
    if speakers:
        speaker_list = [n.strip() for n in speakers.split(",")]

    # 确定输出路径
    audio_path = Path(audio_file)
    if output:
        output_dir = Path(output)
        if output_dir.is_dir() or format == "all":
            output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = audio_path.parent

    base_name = audio_path.stem

    try:
        # 加载模型
        console.print("[bold]步骤 1/2: 加载模型[/bold]")
        whisper_model, diarize_pipeline = load_models(
            model_size=model,
            device=device,
            hf_token=hf_token,
        )
        embedding_inference = None
        if embedding_align:
            embedding_inference = load_embedding_inference(
                embedding_model=embedding_model,
                device=device,
                hf_token=hf_token,
            )

        # 转录音频
        console.print("\n[bold]步骤 2/2: 转录音频[/bold]")
        segments = transcribe_audio(
            audio_file,
            whisper_model,
            diarize_pipeline,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            auto_speakers=auto_speakers,
            chunk_seconds=diarize_chunk_minutes * 60 if diarize_chunk_minutes else None,
            overlap_seconds=diarize_overlap_seconds,
            diarize_stereo=diarize_stereo,
            split_by_diarization=split_by_diarization,
            preprocess=preprocess,
            denoise=denoise,
            highpass_hz=highpass_hz,
            loudnorm=loudnorm,
            embedding_inference=embedding_inference,
            embedding_align=embedding_align,
            embedding_min_duration=embedding_min_duration,
            embedding_similarity_threshold=embedding_similarity_threshold,
            batch_size=batch_size,
        )

        if not segments:
            console.print("[red]错误: 未能识别出任何内容[/red]")
            return

        console.print(f"\n[green]转录完成! 共 {len(segments)} 个片段[/green]\n")

        speaker_names = build_speaker_name_map(
            speaker_list,
            segments,
            auto_map=auto_map_speakers,
        )

        # 显示结果预览
        display_result(segments[:5], speaker_names)
        if len(segments) > 5:
            console.print(f"[dim]... 还有 {len(segments) - 5} 个片段[/dim]\n")

        # 输出结果
        if format == "text" or format == "all":
            out_path = output_dir / f"{base_name}.txt" if format == "all" or not output else output
            output_text(segments, speaker_names, str(out_path))

        if format == "srt" or format == "all":
            out_path = output_dir / f"{base_name}.srt" if format == "all" or not output else output
            output_srt(segments, speaker_names, str(out_path))

        if format == "json" or format == "all":
            out_path = output_dir / f"{base_name}.json" if format == "all" or not output else output
            output_json(segments, speaker_names, str(out_path))

        console.print("\n[bold green]处理完成![/bold green]")

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()
