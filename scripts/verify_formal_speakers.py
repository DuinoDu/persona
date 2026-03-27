#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run_feature_report(audio: Path, section_dir: Path, report_path: Path) -> None:
    cmd = [
        'python', 'scripts/check_audio_speaker_features.py',
        '--audio', str(audio),
        '--dir', str(section_dir),
        '--out', str(report_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description='Run speaker-feature verification for formal transcript sections.')
    ap.add_argument('--audio', required=True)
    ap.add_argument('--dir', required=True, help='Formal transcript directory containing 00_开场.json and *_连麦.json')
    ap.add_argument('--report', required=True)
    ap.add_argument('--summary', required=True)
    ap.add_argument('--delta-threshold', type=float, default=0.001, help='Flag calls with guest-host delta <= threshold')
    args = ap.parse_args()

    audio = Path(args.audio)
    section_dir = Path(args.dir)
    report_path = Path(args.report)
    summary_path = Path(args.summary)

    run_feature_report(audio, section_dir, report_path)

    report = json.loads(report_path.read_text(encoding='utf-8'))
    suspects = []
    for item in report.get('calls', []):
        delta = item.get('delta_guest_minus_host')
        if delta is None or delta <= args.delta_threshold:
            suspects.append({
                'file': item['file'],
                'persona': item['persona'],
                'host_mean_distance_to_host_ref': item.get('host_mean_distance_to_host_ref'),
                'guest_mean_distance_to_host_ref': item.get('guest_mean_distance_to_host_ref'),
                'delta_guest_minus_host': delta,
                'sample_counts': item.get('sample_counts', {}),
            })

    summary = {
        'audio_file': str(audio),
        'section_dir': str(section_dir),
        'report_file': str(report_path),
        'delta_threshold': args.delta_threshold,
        'suspect_count': len(suspects),
        'suspects': suspects,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
