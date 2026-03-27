JSON ?=

.PHONY: generate-video

generate-video:
ifndef JSON
	@echo "Usage: make generate-video JSON=<path-to-transcript.json>"
	@echo "Example: make generate-video JSON=../data/03_transcripts/曲曲2026/005/01_医考培训老师_连麦.json"
	@exit 1
endif
	node scripts/transform-captions.mjs "$(JSON)"
	npx remotion render SubtitleVideo out/video.mp4 --concurrency=4
	@echo "Done: out/video.mp4"
