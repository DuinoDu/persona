# ============================================================
# QuQu YouTube Live Stream Processing Pipeline
# ============================================================
#
# Workflow:
#   data/01_downloads     make step1-download
#         |
#         | scripts/02_split_audio.py
#         v
#   data/02_audio_splits  make step2-split
#         |
#         | scripts/03_batch_transcribe.sh (speech2text)
#         v
#   data/02_audio_splits/*.json
#         |
#         | scripts/04_merge_transcripts.py
#         v
#   data/03_transcripts   make step3-transcribe + make step4-merge
#         |
#         | scripts/05_extract_conversations.py
#         v
#   data/04_conversations make step5-extract
#
# ============================================================

PLAYLIST_URL ?= https://www.youtube.com/watch?v=Vm7NnjYjOeY&list=PLJlZhpX8XtgFCrpjUF-ToYHnrUYUmpWXI
PLAYLIST     ?= $(shell ls data/01_downloads/ | grep -v downloaded.txt | head -1)
BROWSER      ?= firefox

.PHONY: help step1-download step2-split step3-transcribe step4-merge step5-extract pipeline clean-tmp

help:
	@echo "QuQu YouTube Processing Pipeline"
	@echo "================================="
	@echo ""
	@echo "  make step1-download     Download audio from YouTube playlist"
	@echo "  make step2-split        Split long audio into 2h chunks"
	@echo "  make step3-transcribe   Run speech2text on all audio splits"
	@echo "  make step4-merge        Merge part JSONs by date"
	@echo "  make step5-extract      Extract conversations from transcripts"
	@echo ""
	@echo "  make pipeline           Run full pipeline (step2 -> step5)"
	@echo "  make pipeline-all       Run full pipeline including download"
	@echo "  make status             Show data counts at each stage"
	@echo ""
	@echo "  make serve-mp3          Start HTTP server + Cloudflare tunnel"
	@echo ""

status:
	@echo "Pipeline Status"
	@echo "==============="
	@echo "01_downloads  MP3:  $$(find data/01_downloads -name '*.mp3' 2>/dev/null | wc -l)"
	@echo "02_splits     MP3:  $$(find data/02_audio_splits -name '*.mp3' 2>/dev/null | wc -l)"
	@echo "02_splits     JSON: $$(find data/02_audio_splits -name '*.json' 2>/dev/null | wc -l)"
	@echo "03_transcripts JSON: $$(find data/03_transcripts -name '*.json' 2>/dev/null | wc -l)"
	@echo "04_conversations JSON: $$(find data/04_conversations -name '*.json' 2>/dev/null | wc -l)"

# Step 1: Download audio
step1-download:
	@echo "=== Step 1: Download Audio ==="
	./scripts/01_download_audio.sh "$(PLAYLIST_URL)" "data/01_downloads" "$(BROWSER)"

# Step 2: Split long audio into 2h chunks
step2-split:
	@echo "=== Step 2: Split Audio ==="
	uv run python scripts/02_split_audio.py data/01_downloads data/02_audio_splits

# Step 3: Run speech2text transcription
step3-transcribe:
	@echo "=== Step 3: Transcribe Audio ==="
	INPUT_DIR=data/02_audio_splits ./scripts/03_batch_transcribe.sh

# Step 4: Merge part JSONs
step4-merge:
	@echo "=== Step 4: Merge Transcripts ==="
	uv run python scripts/04_merge_transcripts.py --input-dir data/02_audio_splits --output-dir data/03_transcripts

# Step 5: Extract conversations
step5-extract:
	@echo "=== Step 5: Extract Conversations ==="
	uv run python scripts/05_extract_conversations.py --input-dir data/03_transcripts --output-dir data/04_conversations

# Full pipeline (without download)
pipeline: step2-split step3-transcribe step4-merge step5-extract
	@echo ""
	@echo "=== Pipeline Complete ==="
	@$(MAKE) status

# Full pipeline including download
pipeline-all: step1-download pipeline

# Serve MP3 files via HTTP + Cloudflare tunnel
serve-mp3:
	@SERVE_DIR="data/02_audio_splits" ./scripts/serve_mp3.sh

# Clean temporary files
clean-tmp:
	rm -f temp_*.json conversation_analysis*.json *.log
