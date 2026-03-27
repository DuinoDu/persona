import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import path from "path";
import { loadSingleManifest } from "@/lib/singleManifest";
import { getPlaybackPositions } from "@/lib/playbackProgress";
import { hasPartDataset, listPartsByDate } from "@/lib/partIndex";

const MAX_LIMIT = 50;
const DEFAULT_LIMIT = 10;
const SINGLE_AUDIO_ID = "single-audio";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const requestedDate = searchParams.get("date");

  if (requestedDate && hasPartDataset()) {
    const parts = listPartsByDate(requestedDate);
    const progress = getPlaybackPositions(parts.map((part) => part.id));
    return NextResponse.json(
      {
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
      },
      {
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  }

  const manifestItems = loadSingleManifest();
  if (manifestItems) {
    return NextResponse.json({
      items: manifestItems,
      nextCursor: null,
    });
  }

  const singleAudioFilename = process.env.SINGLE_AUDIO_FILENAME;
  if (singleAudioFilename) {
    const base = path.basename(singleAudioFilename, path.extname(singleAudioFilename));
    const dateMatch = base.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
    const date = dateMatch
      ? `${dateMatch[1]}年${dateMatch[2]}月${dateMatch[3]}日`
      : "单文件";

    return NextResponse.json({
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
  const limit = Number.isFinite(limitParam) ? Math.min(Math.max(limitParam, 1), MAX_LIMIT) : DEFAULT_LIMIT;
  const cursor = searchParams.get("cursor");

  const audios = await prisma.audio.findMany({
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: limit + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
  });

  const hasMore = audios.length > limit;
  const items = hasMore ? audios.slice(0, limit) : audios;
  const nextCursor = hasMore ? items[items.length - 1]?.id ?? null : null;

  return NextResponse.json({ items, nextCursor });
}
