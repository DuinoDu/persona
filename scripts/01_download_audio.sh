#!/bin/bash
# Download YouTube playlist audio as MP3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYLIST_URL="${1:-https://www.youtube.com/watch?v=zSVJkfq-wnk&list=PLJlZhpX8XtgGbns1uS4HPfIhqvg_zfWaU}"
OUTPUT_DIR="${2:-data/01_downloads}"
BROWSER="${3:-firefox}"

echo "=================================="
echo "YouTube Playlist Audio Downloader"
echo "=================================="
echo "Playlist: $PLAYLIST_URL"
echo "Output: $OUTPUT_DIR"
echo "Browser: $BROWSER"
echo ""

# Use local .venv
YTDLP="$SCRIPT_DIR/../.venv/bin/yt-dlp"

# Check for browser cookies
echo "Extracting cookies from $BROWSER..."

unset http_proxy https_proxy all_proxy
"$YTDLP" \
  --no-js-runtimes \
  --js-runtimes node \
  --cookies-from-browser "$BROWSER" \
  --print "cookies" 2>&1 | head -1 | grep -q "Extracted" && echo "Cookies extracted successfully!" || echo "Warning: May have issues extracting cookies"

echo ""
echo "Starting download..."
echo ""

"$YTDLP" \
  --no-js-runtimes \
  --js-runtimes node \
  --extract-audio \
  --audio-format mp3 \
  --audio-quality 0 \
  --cookies-from-browser "$BROWSER" \
  -o "$OUTPUT_DIR/%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s" \
  --download-archive "$OUTPUT_DIR/downloaded.txt" \
  --ignore-errors \
  --continue \
  "$PLAYLIST_URL"

echo ""
echo "Download complete! Files saved to: $OUTPUT_DIR"
