#!/usr/bin/env python3
import argparse
from modelscope import snapshot_download

parser = argparse.ArgumentParser()
parser.add_argument("model_id")
parser.add_argument("--cache-dir", required=True)
args = parser.parse_args()

path = snapshot_download(args.model_id, cache_dir=args.cache_dir)
print(path)
