import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import fs from "fs";
import path from "path";
import { execSync } from "child_process";
import { isSingleMode } from "@/lib/singleManifest";

// Support both v1 (flat) and v2 (meta-wrapped) JSON formats
interface RawTextJsonV1 {
  date?: string;
  date_original?: string;
  tag?: string;
  guest_tag?: string;
  audience_tag?: string;
  viewer_tag?: string;
  start_time: number;
  end_time: number;
}

interface RawTextJsonV2 {
  meta: {
    source_file?: string;
    date?: string;
    date_original?: string;
    callin_index?: number;
    start_time: number;
    end_time: number;
    duration_seconds?: number;
    guest_tag?: string;
    tag?: string;
    audience_tag?: string;
    viewer_tag?: string;
    host_speaker_label?: string;
    guest_speaker_labels?: string[];
    num_turns?: number;
  };
  segments: unknown[];
}

type RawTextJson = RawTextJsonV1 | RawTextJsonV2;

function isV2(json: RawTextJson): json is RawTextJsonV2 {
  return "meta" in json && typeof (json as RawTextJsonV2).meta === "object";
}

function getMeta(json: RawTextJson) {
  if (isV2(json)) {
    return {
      start_time: json.meta.start_time,
      end_time: json.meta.end_time,
      date: json.meta.date,
      date_original: json.meta.date_original,
      source_file: json.meta.source_file,
      tag: json.meta.tag,
      guest_tag: json.meta.guest_tag,
      audience_tag: json.meta.audience_tag,
      viewer_tag: json.meta.viewer_tag,
    };
  }
  return {
    start_time: json.start_time,
    end_time: json.end_time,
    date: (json as RawTextJsonV1).date,
    date_original: (json as RawTextJsonV1).date_original,
    source_file: undefined as string | undefined,
    tag: (json as RawTextJsonV1).tag,
    guest_tag: (json as RawTextJsonV1).guest_tag,
    audience_tag: (json as RawTextJsonV1).audience_tag,
    viewer_tag: (json as RawTextJsonV1).viewer_tag,
  };
}

function formatTimestamp(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}${m.toString().padStart(2, "0")}${s.toString().padStart(2, "0")}`;
}

function formatTimeDisplay(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatFfmpegTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 3600 % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`;
}

function extractDateFromString(str: string): string | null {
  const cnMatch = str.match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/);
  if (cnMatch) return `${cnMatch[1]}\u5e74${cnMatch[2]}\u6708${cnMatch[3]}\u65e5`;
  const compactMatch = str.match(/(\d{4})(\d{2})(\d{2})/);
  if (!compactMatch) return null;
  const [, y, m, d] = compactMatch;
  return `${Number(y)}\u5e74${Number(m)}\u6708${Number(d)}\u65e5`;
}

function extractTagFromFilename(filename: string): string | null {
  const base = path.basename(filename).replace(/\.[^/.]+$/, "");
  const match = base.match(/^(.+?)_(\d{6})[-_](\d{6})_(.+)$/);
  return match ? match[4] : null;
}

function normalizeTag(value?: string | null): string | null {
  if (!value) return null;
  const trimmed = String(value).trim();
  return trimmed.length > 0 ? trimmed : null;
}

function sanitizeTagForFilename(tag: string): string {
  return tag.replace(/[\/\\]/g, "-").replace(/\s+/g, " ").trim();
}

function listFilesRecursive(dir: string, ext: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...listFilesRecursive(fullPath, ext));
    } else if (entry.isFile() && entry.name.endsWith(ext)) {
      files.push(fullPath);
    }
  }
  return files;
}

export async function POST() {
  if (isSingleMode()) {
    return NextResponse.json({
      skipped: true,
      reason: "single mode",
    });
  }

  const baseDir = path.join(process.cwd(), "public", "audios");
  const rawTextsDir =
    process.env.RAW_TEXTS_DIR || path.join(baseDir, "raw_texts");
  const rawAudiosDir =
    process.env.RAW_AUDIOS_DIR || path.join(baseDir, "raw_audios");
  const conversationsDir = path.join(baseDir, "conversations");

  if (!fs.existsSync(rawTextsDir)) {
    return NextResponse.json({ error: "raw_texts directory not found" }, { status: 404 });
  }

  if (!fs.existsSync(conversationsDir)) {
    fs.mkdirSync(conversationsDir, { recursive: true });
  }

  const rawAudioFiles = fs.existsSync(rawAudiosDir)
    ? listFilesRecursive(rawAudiosDir, ".mp3")
    : [];

  const jsonFiles = listFilesRecursive(rawTextsDir, ".json");
  const results = { added: 0, updated: 0, skipped: 0, errors: [] as string[] };

  for (const jsonPath of jsonFiles) {
    const jsonFile = path.basename(jsonPath);
    const jsonContent = JSON.parse(fs.readFileSync(jsonPath, "utf-8")) as RawTextJson;

    const meta = getMeta(jsonContent);

    // Resolve date: try date_original, source_file, then filename
    let dateStr: string | null = null;

    if (meta.date_original) {
      dateStr = extractDateFromString(meta.date_original);
    }

    if (!dateStr && meta.source_file) {
      dateStr = extractDateFromString(meta.source_file);
    }

    if (!dateStr && meta.date) {
      dateStr = extractDateFromString(meta.date);
    }

    if (!dateStr) {
      dateStr = extractDateFromString(jsonFile);
    }

    if (!dateStr) {
      // Try parent directory name
      dateStr = extractDateFromString(path.basename(path.dirname(jsonPath)));
    }

    if (!dateStr) {
      results.errors.push(`Cannot determine date for: ${jsonFile}`);
      continue;
    }

    const { start_time, end_time } = meta;

    // Resolve tag
    const resolvedTag =
      normalizeTag(meta.tag) ||
      normalizeTag(meta.guest_tag) ||
      normalizeTag(meta.audience_tag) ||
      normalizeTag(meta.viewer_tag) ||
      normalizeTag(extractTagFromFilename(jsonFile));

    const safeTag = resolvedTag ? sanitizeTagForFilename(resolvedTag) : "unknown";
    const startTs = formatTimestamp(start_time);
    const endTs = formatTimestamp(end_time);
    const outputFilename = `${dateStr}_${startTs}_${endTs}_${safeTag}.mp3`;
    const outputPath = path.join(conversationsDir, outputFilename);
    const startDisplay = formatTimeDisplay(start_time);
    const endDisplay = formatTimeDisplay(end_time);

    // Check if already in database
    const existing = await prisma.audio.findUnique({ where: { filename: outputFilename } });
    if (existing) {
      results.skipped++;
      continue;
    }

    const existingByTime = await prisma.audio.findFirst({
      where: { date: dateStr, startTime: startDisplay, endTime: endDisplay },
    });

    if (safeTag === "unknown" && existingByTime) {
      results.skipped++;
      continue;
    }

    // Check if output file already exists
    if (!fs.existsSync(outputPath)) {
      if (existingByTime?.filename) {
        const oldPath = path.join(conversationsDir, existingByTime.filename);
        if (fs.existsSync(oldPath)) {
          fs.renameSync(oldPath, outputPath);
        }
      }

      if (!fs.existsSync(outputPath)) {
        // Find matching raw audio file by date
        const rawAudioPath = rawAudioFiles.find((filePath) =>
          path.basename(filePath).includes(dateStr!)
        );
        if (!rawAudioPath) {
          results.errors.push(`No raw audio found for date: ${dateStr}`);
          continue;
        }

        const duration = end_time - start_time;

        try {
          execSync(
            `ffmpeg -i "${rawAudioPath}" -ss ${formatFfmpegTime(start_time)} -t ${duration} -c copy "${outputPath}" -y`,
            { stdio: "pipe" }
          );
        } catch (err) {
          results.errors.push(`ffmpeg error for ${jsonFile}: ${err}`);
          continue;
        }
      }
    }

    // Add to database
    if (existingByTime) {
      if (
        existingByTime.filename === outputFilename &&
        existingByTime.personTag === safeTag
      ) {
        results.skipped++;
        continue;
      }
      await prisma.audio.update({
        where: { id: existingByTime.id },
        data: {
          filename: outputFilename,
          filepath: `/audios/conversations/${outputFilename}`,
          personTag: safeTag,
        },
      });
      results.updated++;
    } else {
      await prisma.audio.create({
        data: {
          filename: outputFilename,
          filepath: `/audios/conversations/${outputFilename}`,
          date: dateStr,
          startTime: startDisplay,
          endTime: endDisplay,
          personTag: safeTag,
        },
      });
      results.added++;
    }
  }

  return NextResponse.json(results);
}
