#!/usr/bin/env python3
"""
Batch speech-to-text for local MP3 files using a single Cloudflare Tunnel.

Walks an input directory, keeps the relative folder structure, and writes
transcripts to the output directory with the chosen format.
"""

import argparse
import os
import sys
import time
import urllib.parse
from pathlib import Path
import http.server
import socketserver

from tts import API_TOKEN, SpeechToText


def start_file_server(directory: Path, port: int):
    """Start a simple HTTP server rooted at directory."""
    os.chdir(directory)

    class ReuseTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    handler = http.server.SimpleHTTPRequestHandler
    httpd = ReuseTCPServer(("", port), handler)
    httpd.daemon_threads = True
    return httpd


def start_cloudflare_tunnel(local_port: int):
    """Start Cloudflare Tunnel and return (process, public_url, log_path)."""
    import subprocess
    import tempfile
    from pathlib import Path as _Path

    log_file = tempfile.NamedTemporaryFile(prefix="cloudflared-", suffix=".log", delete=False)
    log_path = Path(log_file.name)
    log_file.close()

    cmd = [
        str(_Path.home() / ".local" / "bin" / "cloudflared"),
        "tunnel",
        "--url",
        f"http://localhost:{local_port}",
        "--logfile",
        str(log_path),
        "--loglevel",
        "info",
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    public_url = None
    for _ in range(120):
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            text = ""

        if "trycloudflare.com" in text:
            import re
            match = re.search(r"https://[A-Za-z0-9-]+\\.trycloudflare\\.com", text)
            if match:
                public_url = match.group(0)
                break

        time.sleep(0.5)

    if not public_url:
        process.terminate()
        raise RuntimeError("Failed to obtain Cloudflare Tunnel URL")

    return process, public_url, log_path


def iter_mp3_files(root: Path):
    return sorted(p for p in root.rglob("*.mp3") if p.is_file())


def build_public_url(base: str, rel_path: Path) -> str:
    rel_posix = rel_path.as_posix()
    quoted = urllib.parse.quote(rel_posix, safe="/")
    return f"{base}/{quoted}"


def output_path_for(input_root: Path, output_root: Path, src_file: Path, fmt: str) -> Path:
    rel = src_file.relative_to(input_root)
    suffix = {"text": ".txt", "json": ".json", "srt": ".srt"}[fmt]
    return output_root / rel.with_suffix(suffix)


def main():
    parser = argparse.ArgumentParser(description="Batch TTS with Cloudflare Tunnel")
    parser.add_argument(
        "--input-dir",
        default="audio_splits",
        help="Directory that contains mp3 files",
    )
    parser.add_argument(
        "--output-dir",
        default="01_stt",
        help="Directory to write transcripts",
    )
    parser.add_argument(
        "-l",
        "--language",
        default="zh",
        help="Output language (default: zh)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "srt"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--no-speaker",
        action="store_true",
        help="Disable speaker recognition",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=8765,
        help="Local HTTP server port",
    )
    parser.add_argument(
        "--token",
        default=API_TOKEN,
        help="RecCloud API token",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing outputs",
    )

    args = parser.parse_args()

    input_root = Path(args.input_dir).resolve()
    output_root = Path(args.output_dir).resolve()

    if not input_root.exists():
        print(f"Input dir not found: {input_root}", file=sys.stderr)
        sys.exit(1)

    mp3_files = iter_mp3_files(input_root)
    if not mp3_files:
        print(f"No mp3 files found under: {input_root}", file=sys.stderr)
        sys.exit(1)

    output_root.mkdir(parents=True, exist_ok=True)

    original_dir = Path.cwd()
    server = None
    tunnel_process = None

    try:
        server = start_file_server(input_root, args.local_port)

        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        tunnel_process, public_url, log_path = start_cloudflare_tunnel(args.local_port)
        time.sleep(3)

        client = SpeechToText(token=args.token)

        failures = []
        total = len(mp3_files)

        for idx, src in enumerate(mp3_files, 1):
            rel = src.relative_to(input_root)
            out_path = output_path_for(input_root, output_root, src, args.format)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            if out_path.exists() and not args.overwrite:
                print(f"[{idx}/{total}] skip (exists): {rel}")
                continue

            file_url = build_public_url(public_url, rel)
            print(f"[{idx}/{total}] transcribe: {rel}")

            try:
                task_data = client.create_task(
                    url=file_url,
                    language=args.language,
                    speaker_recognition=not args.no_speaker,
                )
                result_data = client.wait_for_result(task_data["task_id"])
                output = client.format_result(result_data, output_format=args.format)
                out_path.write_text(output, encoding="utf-8")
            except Exception as exc:
                failures.append((rel, str(exc)))
                print(f"  failed: {rel} | {exc}", file=sys.stderr)

        missing = []
        for src in mp3_files:
            out_path = output_path_for(input_root, output_root, src, args.format)
            if not out_path.exists():
                missing.append(out_path)

        if failures:
            print(f"Failures: {len(failures)}", file=sys.stderr)
        if missing:
            print(f"Missing outputs: {len(missing)}", file=sys.stderr)

        if failures or missing:
            sys.exit(1)

        print(f"Done. Outputs: {len(mp3_files)}")

    finally:
        if tunnel_process:
            tunnel_process.terminate()
        if "log_path" in locals():
            try:
                Path(log_path).unlink()
            except FileNotFoundError:
                pass
        if server:
            server.shutdown()
        os.chdir(original_dir)


if __name__ == "__main__":
    main()
