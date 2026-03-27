#!/usr/bin/env python3
"""
Split an input MP3 into fixed-length chunks, run speech2text on each chunk,
merge JSON results back to original timeline, and delete chunk files.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple


def run(cmd: List[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(cmd)}):\n{result.stderr.strip()}"
        )


def ffprobe_duration(file_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def split_audio(input_file: Path, output_dir: Path, chunk_seconds: int) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = output_dir / "part%03d.mp3"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        "-c",
        "copy",
        str(output_pattern),
    ]
    run(cmd)
    return sorted(output_dir.glob("part*.mp3"))


def transcribe_chunk(
    python_bin: Path,
    speech2text_root: Path,
    chunk_file: Path,
    output_json: Path,
    transcribe_args: List[str],
) -> None:
    cmd = [
        str(python_bin),
        "-m",
        "speech2text.transcribe",
        str(chunk_file),
        "-f",
        "json",
        "-o",
        str(output_json),
    ] + transcribe_args
    run(cmd, cwd=speech2text_root)


def merge_json_chunks(
    chunk_jsons: List[Path],
    chunk_durations: List[float],
    output_json: Path,
) -> None:
    merged_segments = []
    speaker_set = set()
    offset = 0.0

    for chunk_json, duration in zip(chunk_jsons, chunk_durations, strict=True):
        with chunk_json.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for seg in data.get("segments", []):
            merged_segments.append(
                {
                    "start": round(seg["start"] + offset, 2),
                    "end": round(seg["end"] + offset, 2),
                    "speaker": seg.get("speaker", "UNKNOWN"),
                    "text": seg.get("text", "").strip(),
                }
            )
            speaker_set.add(seg.get("speaker", "UNKNOWN"))
        offset += duration

    merged_segments.sort(key=lambda s: s["start"])
    output = {"segments": merged_segments, "speakers": sorted(speaker_set)}
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split MP3 into chunks, transcribe each, merge JSON, delete chunks."
    )
    parser.add_argument("input", type=str, help="Input MP3 path")
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=30,
        help="Chunk length in minutes (default: 30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Merged JSON output path (default: <input>.json)",
    )
    parser.add_argument(
        "--speech2text-root",
        type=str,
        default="speech2text",
        help="speech2text project root (default: speech2text)",
    )
    parser.add_argument(
        "--python",
        type=str,
        default=None,
        help="Python executable to use (default: current interpreter)",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Keep split MP3 chunks (default: delete)",
    )
    args, extra_args = parser.parse_known_args()

    input_file = Path(args.input)
    if not input_file.exists():
        raise SystemExit(f"Input not found: {input_file}")

    output_json = Path(args.output) if args.output else input_file.with_suffix(".json")
    speech2text_root = Path(args.speech2text_root).resolve()
    python_bin = Path(args.python).absolute() if args.python else Path(sys.executable)

    chunk_seconds = max(1, args.chunk_minutes * 60)
    transcribe_args = extra_args
    if transcribe_args and transcribe_args[0] == "--":
        transcribe_args = transcribe_args[1:]

    chunk_files: List[Path] = []
    chunk_jsons: List[Path] = []
    chunk_durations: List[float] = []

    with tempfile.TemporaryDirectory(prefix="stt_chunks_") as tmpdir:
        tmp_dir = Path(tmpdir)
        chunk_files = split_audio(input_file, tmp_dir, chunk_seconds)
        if not chunk_files:
            raise SystemExit("No chunks produced by ffmpeg.")

        for chunk in chunk_files:
            chunk_json = tmp_dir / f"{chunk.stem}.json"
            transcribe_chunk(
                python_bin=python_bin,
                speech2text_root=speech2text_root,
                chunk_file=chunk,
                output_json=chunk_json,
                transcribe_args=transcribe_args,
            )
            chunk_jsons.append(chunk_json)
            chunk_durations.append(ffprobe_duration(chunk))

        merge_json_chunks(chunk_jsons, chunk_durations, output_json)

        if args.keep_chunks:
            for chunk in chunk_files:
                target = input_file.parent / chunk.name
                chunk.replace(target)
        else:
            for chunk in chunk_files:
                if chunk.exists():
                    chunk.unlink()

    print(f"✅ Merged JSON saved: {output_json}")


if __name__ == "__main__":
    main()
