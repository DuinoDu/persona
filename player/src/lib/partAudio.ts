import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import type { PartRecord } from "@/lib/partIndex";

const execFileAsync = promisify(execFile);
const generationLocks = new Map<string, Promise<void>>();

function safePathSegment(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, " ").trim();
}

export function getGeneratedPartRelativePath(part: PartRecord) {
  const dateDir = safePathSegment(part.dateLabel);
  return `generated-parts/${dateDir}/${part.id}.mp3`;
}

function getGeneratedPartAbsolutePath(part: PartRecord) {
  return path.join(process.cwd(), "public", getGeneratedPartRelativePath(part));
}

async function generatePartAudio(part: PartRecord) {
  if (!part.sourceAudioPath) {
    throw new Error(`Raw source audio not found for ${part.dateLabel} / ${part.title}`);
  }

  const targetPath = getGeneratedPartAbsolutePath(part);
  if (fs.existsSync(targetPath) && fs.statSync(targetPath).size > 0) {
    return;
  }

  fs.mkdirSync(path.dirname(targetPath), { recursive: true });

  const duration = Math.max(0.1, part.endSec - part.startSec);
  const args = [
    "-y",
    "-ss",
    String(part.startSec),
    "-t",
    String(duration),
    "-i",
    part.sourceAudioPath,
    "-vn",
    "-c:a",
    "copy",
    targetPath,
  ];

  try {
    await execFileAsync("ffmpeg", args, { maxBuffer: 10 * 1024 * 1024 });
  } catch {
    await execFileAsync(
      "ffmpeg",
      [
        "-y",
        "-ss",
        String(part.startSec),
        "-t",
        String(duration),
        "-i",
        part.sourceAudioPath,
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        targetPath,
      ],
      { maxBuffer: 10 * 1024 * 1024 }
    );
  }
}

export async function ensureGeneratedPartAudio(part: PartRecord) {
  const targetPath = getGeneratedPartAbsolutePath(part);
  if (fs.existsSync(targetPath) && fs.statSync(targetPath).size > 0) {
    return targetPath;
  }

  const existing = generationLocks.get(part.id);
  if (existing) {
    await existing;
    return targetPath;
  }

  const pending = generatePartAudio(part).finally(() => {
    generationLocks.delete(part.id);
  });
  generationLocks.set(part.id, pending);
  await pending;
  return targetPath;
}
