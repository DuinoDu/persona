const { PrismaClient } = require('@prisma/client');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const prisma = new PrismaClient();

function isV2(json) {
  return "meta" in json && typeof json.meta === "object";
}

function getMeta(json) {
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
    date: json.date,
    date_original: json.date_original,
    source_file: undefined,
    tag: json.tag,
    guest_tag: json.guest_tag,
    audience_tag: json.audience_tag,
    viewer_tag: json.viewer_tag,
  };
}

function formatTimestamp(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}${m.toString().padStart(2, "0")}${s.toString().padStart(2, "0")}`;
}

function formatTimeDisplay(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatFfmpegTime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 3600 % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toFixed(2).padStart(5, "0")}`;
}

function extractDateFromString(str) {
  const cnMatch = str.match(/(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5/);
  if (cnMatch) return `${cnMatch[1]}\u5e74${cnMatch[2]}\u6708${cnMatch[3]}\u65e5`;
  const compactMatch = str.match(/(\d{4})(\d{2})(\d{2})/);
  if (!compactMatch) return null;
  const [, y, mo, d] = compactMatch;
  return `${Number(y)}\u5e74${Number(mo)}\u6708${Number(d)}\u65e5`;
}

function normalizeTag(value) {
  if (!value) return null;
  const trimmed = String(value).trim();
  return trimmed.length > 0 ? trimmed : null;
}

function sanitizeTagForFilename(tag) {
  return tag.replace(/[\/\\]/g, "-").replace(/\s+/g, " ").trim();
}

function listFilesRecursive(dir, ext) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
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

async function main() {
  const baseDir = path.join(process.cwd(), "public", "audios");
  const rawTextsDir = process.env.RAW_TEXTS_DIR || path.join(baseDir, "raw_texts");
  const rawAudiosDir = process.env.RAW_AUDIOS_DIR || path.join(baseDir, "raw_audios");
  const conversationsDir = path.join(baseDir, "conversations");

  console.log(`RAW_TEXTS_DIR: ${rawTextsDir}`);
  console.log(`RAW_AUDIOS_DIR: ${rawAudiosDir}`);

  if (!fs.existsSync(rawTextsDir)) {
    console.error("raw_texts directory not found");
    process.exit(1);
  }

  if (!fs.existsSync(conversationsDir)) {
    fs.mkdirSync(conversationsDir, { recursive: true });
  }

  const rawAudioFiles = fs.existsSync(rawAudiosDir)
    ? listFilesRecursive(rawAudiosDir, ".mp3")
    : [];

  console.log(`Found ${rawAudioFiles.length} raw audio files`);

  const jsonFiles = listFilesRecursive(rawTextsDir, ".json");
  console.log(`Found ${jsonFiles.length} JSON files`);

  const results = { added: 0, updated: 0, skipped: 0, errors: 0, noAudio: 0 };

  for (let i = 0; i < jsonFiles.length; i++) {
    const jsonPath = jsonFiles[i];
    const jsonFile = path.basename(jsonPath);

    try {
      const jsonContent = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));
      const meta = getMeta(jsonContent);

      // Resolve date
      let dateStr = null;
      if (meta.date_original) dateStr = extractDateFromString(meta.date_original);
      if (!dateStr && meta.source_file) dateStr = extractDateFromString(meta.source_file);
      if (!dateStr && meta.date) dateStr = extractDateFromString(meta.date);
      if (!dateStr) dateStr = extractDateFromString(jsonFile);
      if (!dateStr) dateStr = extractDateFromString(path.basename(path.dirname(jsonPath)));

      if (!dateStr) {
        results.errors++;
        continue;
      }

      const { start_time, end_time } = meta;
      const resolvedTag =
        normalizeTag(meta.tag) ||
        normalizeTag(meta.guest_tag) ||
        normalizeTag(meta.audience_tag) ||
        normalizeTag(meta.viewer_tag) ||
        "unknown";
      const safeTag = sanitizeTagForFilename(resolvedTag);
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

      // Cut audio if not exists
      if (!fs.existsSync(outputPath)) {
        const rawAudioPath = rawAudioFiles.find((filePath) =>
          path.basename(filePath).includes(dateStr)
        );
        if (!rawAudioPath) {
          results.noAudio++;
          continue;
        }

        const duration = end_time - start_time;
        try {
          execSync(
            `ffmpeg -i "${rawAudioPath}" -ss ${formatFfmpegTime(start_time)} -t ${duration} -c copy "${outputPath}" -y`,
            { stdio: "pipe" }
          );
        } catch (err) {
          results.errors++;
          continue;
        }
      }

      // Add to database
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

      if ((i + 1) % 100 === 0) {
        console.log(`Progress: ${i + 1}/${jsonFiles.length} (added=${results.added})`);
      }
    } catch (err) {
      results.errors++;
    }
  }

  console.log(`\nDone! added=${results.added} skipped=${results.skipped} errors=${results.errors} noAudio=${results.noAudio}`);
  await prisma.$disconnect();
}

main().catch(console.error);
