import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { loadSingleManifest } from "@/lib/singleManifest";
import { getPartById } from "@/lib/partIndex";
import { setPlaybackPosition } from "@/lib/playbackProgress";

const SINGLE_AUDIO_ID = "single-audio";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();
  const nextPosition = body.lastPosition ?? 0;

  const manifestItems = loadSingleManifest();
  if (manifestItems && manifestItems.some((item) => item.id === id)) {
    return NextResponse.json({
      id,
      lastPosition: nextPosition,
    });
  }

  if (process.env.SINGLE_AUDIO_FILENAME && id === SINGLE_AUDIO_ID) {
    return NextResponse.json({
      id,
      lastPosition: nextPosition,
    });
  }

  if (id.startsWith("part_") || getPartById(id)) {
    return NextResponse.json({
      id,
      lastPosition: setPlaybackPosition(id, Number(nextPosition)),
    });
  }

  try {
    const audio = await prisma.audio.update({
      where: { id },
      data: { lastPosition: nextPosition },
    });

    return NextResponse.json(audio);
  } catch {
    return NextResponse.json({
      id,
      lastPosition: Number(nextPosition) || 0,
      skipped: true,
    });
  }
}
