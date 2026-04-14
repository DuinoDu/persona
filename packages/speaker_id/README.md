# Ququ Speaker ID Tool

This repository contains a first-pass local CLI for speaker-ID correction on
Ququ call parts.

The baseline uses:

- sentence-level slicing from `data/03_parts`
- source audio from `data/01_downloads`
- raw transcript overlap hints from `data/02_transcripts`
- spectrum-derived features (`MFCC`, log-mel, spectral contrast, energy)
- two-speaker clustering + host-bank similarity mapping

The CLI now supports two embedding backends:

- `spectrum`: lightweight baseline, no model download
- `wespeaker`: WeSpeaker pretrained speaker embedding backend, recommended

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

For the WeSpeaker backend:

```bash
pip install -e ".[wespeaker]"
```

## Build the host bank

```bash
ququ-speaker-id build-host-bank --max-parts 300 --max-segments 1200
```

Build the host bank with WeSpeaker:

```bash
ququ-speaker-id build-host-bank --backend wespeaker --max-parts 300 --max-segments 1200
```

## Analyze one part

```bash
ququ-speaker-id analyze-part \
  --backend wespeaker \
  --part-file "/home/duino/ws/ququ/process_youtube/data/03_parts/曲曲2024（全）/57 - 曲曲直播 2024年09月05日 曲曲大女人 美人解忧铺 #曲曲麦肯锡/01_一线单身直播_连麦.json"
```

Render an HTML side-by-side comparison for one part:

```bash
ququ-speaker-id render-html \
  --backend wespeaker \
  --host-bank-path artifacts/host_bank_wespeaker.json \
  --part-file "/home/duino/ws/ququ/process_youtube/data/03_parts/曲曲2022/45 - 曲曲大女人 2022年11月29日 男人其实比你们想象的简单很多 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺_processed/15_安全感低月供谈判女_连麦.json"
```

## Analyze a sample of the dataset

```bash
ququ-speaker-id analyze-dataset --limit 20
```

Outputs are written into `artifacts/`.

Sentence embeddings are cached on disk by default under
`artifacts/embedding_cache/`. Re-running the same part or dataset slice will
reuse cached vectors and report `cache_hits/cache_misses/cache_writes` in the
CLI output.

## Warm the embedding cache

Warm a single part:

```bash
ququ-speaker-id warm-cache \
  --backend wespeaker \
  --part-file "/home/duino/ws/ququ/process_youtube/data/03_parts/曲曲2022/45 - 曲曲大女人 2022年11月29日 男人其实比你们想象的简单很多 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺_processed/15_安全感低月供谈判女_连麦.json"
```

Warm a dataset slice:

```bash
ququ-speaker-id warm-cache --backend wespeaker --limit 20
```

## Clear the embedding cache

Clear all cached embeddings:

```bash
ququ-speaker-id clear-cache
```

Clear only the WeSpeaker namespace:

```bash
ququ-speaker-id clear-cache --backend wespeaker
```

`analyze-dataset` now also writes `dataset_metrics.json` with elapsed time and
cache hit/miss stats.
