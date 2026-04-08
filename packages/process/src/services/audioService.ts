import fs from "fs";
import { ensureGeneratedPartAudio } from "../partAudio";
import { getPartById, hasPartDataset, listAvailableDates, listPartsByDate } from "../partIndex";
import { getPlaybackPositions, setPlaybackPosition } from "../playbackProgress";
import { loadSingleManifest } from "../singleManifest";
import { type JsonServiceResult, jsonResult, type ProcessDbClient } from "./shared";

const MAX_LIMIT = 50;
const DEFAULT_LIMIT = 10;
const SINGLE_AUDIO_ID = "single-audio";

interface AudioByteRange {
  start: number;
  end: number;
}

export type PartAudioStreamOpenResult =
  | {
      ok: false;
      status: number;
      body: {
        filePath?: string;
        fileSize?: number;
        contentLength?: number;
        contentRange?: string;
        range?: AudioByteRange;
        error?: string;
      };
    }
  | {
      ok: true;
      status: 200 | 206;
      stream: fs.ReadStream;
      fileSize: number;
      contentLength: number;
      contentRange: string | null;
    };

function parseAudioByteRange(rangeHeader: string, fileSize: number): AudioByteRange | null {
  const match = rangeHeader.match(/bytes=(\d*)-(\d*)/);
  if (!match) return null;

  const start = match[1] ? Number(match[1]) : 0;
  const end = match[2] ? Number(match[2]) : fileSize - 1;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
    return null;
  }

  return {
    start,
    end: Math.min(end, fileSize - 1),
  };
}

export function listAudioDatesService() {
  return jsonResult({ items: listAvailableDates() });
}

export async function listAudiosService(input: {
  db: ProcessDbClient;
  requestUrl: string;
}) {
  const { searchParams } = new URL(input.requestUrl);
  const requestedDate = searchParams.get("date");

  if (requestedDate && hasPartDataset()) {
    const parts = listPartsByDate(requestedDate);
    const progress = getPlaybackPositions(parts.map((part) => part.id));
    return jsonResult({
      items: parts.map((part) => ({
        id: part.id,
        filename: part.displayFilename,
        filepath: `/api/part-audio/${encodeURIComponent(part.id)}`,
        date: part.dateLabel,
        startTime: part.startTime,
        endTime: part.endTime,
        personTag: part.personTag,
        lastPosition: progress[part.id] ?? 0,
        subtitleId: part.id,
        subtitleFile: part.subtitleFile,
        kind: part.kind,
        title: part.title,
      })),
      nextCursor: null,
    });
  }

  const manifestItems = loadSingleManifest();
  if (manifestItems) {
    return jsonResult({
      items: manifestItems,
      nextCursor: null,
    });
  }

  const singleAudioFilename = process.env.SINGLE_AUDIO_FILENAME;
  if (singleAudioFilename) {
    const base = singleAudioFilename.replace(/\.[^.]+$/, "");
    const dateMatch = base.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
    const date = dateMatch
      ? `${dateMatch[1]}年${dateMatch[2]}月${dateMatch[3]}日`
      : "单文件";

    return jsonResult({
      items: [
        {
          id: SINGLE_AUDIO_ID,
          filename: singleAudioFilename,
          filepath: `/audios/single/${encodeURIComponent(singleAudioFilename)}`,
          date,
          startTime: "00:00:00",
          endTime: "整场",
          personTag: base,
          lastPosition: 0,
        },
      ],
      nextCursor: null,
    });
  }

  const limitParam = Number(searchParams.get("limit"));
  const limit = Number.isFinite(limitParam)
    ? Math.min(Math.max(limitParam, 1), MAX_LIMIT)
    : DEFAULT_LIMIT;
  const cursor = searchParams.get("cursor");

  const audios = await input.db.audio.findMany({
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: limit + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
  });

  const hasMore = audios.length > limit;
  const items = hasMore ? audios.slice(0, limit) : audios;
  const nextCursor = hasMore ? items[items.length - 1]?.id ?? null : null;

  return jsonResult({ items, nextCursor });
}

export async function updateAudioProgressService(input: {
  db: ProcessDbClient;
  audioId: string;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const nextPosition = body.lastPosition ?? 0;
  const id = input.audioId;

  const manifestItems = loadSingleManifest();
  if (manifestItems && manifestItems.some((item) => item.id === id)) {
    return jsonResult({ id, lastPosition: nextPosition });
  }

  if (process.env.SINGLE_AUDIO_FILENAME && id === SINGLE_AUDIO_ID) {
    return jsonResult({ id, lastPosition: nextPosition });
  }

  if (id.startsWith("part_") || getPartById(id)) {
    return jsonResult({
      id,
      lastPosition: setPlaybackPosition(id, Number(nextPosition)),
    });
  }

  try {
    const audio = await input.db.audio.update({
      where: { id },
      data: { lastPosition: nextPosition },
    });
    return jsonResult(audio);
  } catch {
    return jsonResult({
      id,
      lastPosition: Number(nextPosition) || 0,
      skipped: true,
    });
  }
}

export async function resolvePartAudioFileService(input: {
  partId: string;
}): Promise<JsonServiceResult<{ filePath?: string; error?: string }>> {
  const part = getPartById(input.partId);
  if (!part) {
    return jsonResult({ error: "Part not found" }, 404);
  }

  try {
    const filePath = await ensureGeneratedPartAudio(part);
    return jsonResult({ filePath });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: message }, 500);
  }
}

export async function resolvePartAudioStreamService(input: {
  partId: string;
  rangeHeader?: string | null;
}): Promise<
  JsonServiceResult<{
    filePath?: string;
    fileSize?: number;
    contentLength?: number;
    contentRange?: string;
    range?: AudioByteRange;
    error?: string;
  }>
> {
  const resolved = await resolvePartAudioFileService({ partId: input.partId });
  if (resolved.status !== 200 || !resolved.body.filePath) {
    return resolved;
  }

  const filePath = resolved.body.filePath;
  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const rangeHeader = input.rangeHeader?.trim();

  if (rangeHeader) {
    const range = parseAudioByteRange(rangeHeader, fileSize);
    if (!range) {
      return jsonResult(
        {
          error: "Invalid range",
          filePath,
          fileSize,
          contentRange: `bytes */${fileSize}`,
        },
        416
      );
    }

    return jsonResult({
      filePath,
      fileSize,
      range,
      contentLength: range.end - range.start + 1,
      contentRange: `bytes ${range.start}-${range.end}/${fileSize}`,
    }, 206);
  }

  return jsonResult({
    filePath,
    fileSize,
    contentLength: fileSize,
  });
}

export async function openPartAudioStreamService(input: {
  partId: string;
  rangeHeader?: string | null;
}): Promise<PartAudioStreamOpenResult> {
  const resolved = await resolvePartAudioStreamService(input);
  if (!resolved.body.filePath || !resolved.body.fileSize || !resolved.body.contentLength) {
    return {
      ok: false,
      status: resolved.status,
      body: resolved.body,
    };
  }

  const { filePath, fileSize, range, contentLength, contentRange } = resolved.body;
  const stream = range ? fs.createReadStream(filePath, range) : fs.createReadStream(filePath);
  return {
    ok: true,
    status: resolved.status as 200 | 206,
    stream,
    fileSize,
    contentLength,
    contentRange: contentRange ?? null,
  };
}
