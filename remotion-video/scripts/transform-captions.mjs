import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

const transcriptPath = process.argv[2];

if (!transcriptPath) {
  console.error('Usage: node scripts/transform-captions.mjs <path-to-transcript.json>');
  process.exit(1);
}

if (!fs.existsSync(transcriptPath)) {
  console.error(`File not found: ${transcriptPath}`);
  process.exit(1);
}

const transcript = JSON.parse(fs.readFileSync(transcriptPath, 'utf-8'));

// Generate captions
const captions = transcript.sentences.map(sentence => ({
  text: sentence.text,
  startMs: sentence.start * 1000,
  endMs: sentence.end * 1000,
  timestampMs: sentence.start * 1000,
  confidence: 0.95,
}));

fs.writeFileSync(
  path.join('public', 'captions.json'),
  JSON.stringify(captions, null, 2)
);
console.log(`Generated ${captions.length} captions`);

// Extract audio segment
const { start, end, source_file } = transcript.meta;
const transcriptDir = path.dirname(transcriptPath);

// source_file is like "005 - 曲曲現場直播 2026年2月26日 ｜ 曲曲麥肯錫.json"
// MP3 is in data/01_downloads/曲曲2026/ with same name but .mp3
const mp3Name = source_file.replace('.json', '.mp3');

// Find year from transcript path
const yearMatch = transcriptPath.match(/曲曲(\d{4})/);
if (!yearMatch) {
  console.error('Cannot determine year from path');
  process.exit(1);
}
const year = yearMatch[1];

const mp3Path = path.join('/home/duino/ws/ququ/process_youtube/data/01_downloads', `曲曲${year}`, mp3Name);

if (!fs.existsSync(mp3Path)) {
  console.error(`MP3 not found: ${mp3Path}`);
  process.exit(1);
}

const outputPath = path.join('public', 'audio.mp3');
const cmd = `ffmpeg -i "${mp3Path}" -ss ${start} -to ${end} -c copy "${outputPath}" -y`;
execSync(cmd, { stdio: 'pipe' });

console.log(`Extracted audio: ${start}s - ${end}s`);
console.log(`Output: ${outputPath}`);
