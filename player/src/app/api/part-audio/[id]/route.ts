import fs from "fs";
import { Readable } from "stream";
import { NextRequest, NextResponse } from "next/server";
import { ensureGeneratedPartAudio } from "@/lib/partAudio";
import { getPartById } from "@/lib/partIndex";

export const dynamic = "force-dynamic";

function parseRangeHeader(rangeHeader: string, fileSize: number) {
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

async function resolvePartFile(id: string) {
  const part = getPartById(id);
  if (!part) {
    return {
      error: NextResponse.json({ error: "Part not found" }, { status: 404 }),
      filePath: null,
    };
  }

  try {
    const filePath = await ensureGeneratedPartAudio(part);
    return { error: null, filePath };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      error: NextResponse.json({ error: message }, { status: 500 }),
      filePath: null,
    };
  }
}

export async function HEAD(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const resolved = await resolvePartFile(id);
  if (resolved.error || !resolved.filePath) {
    return resolved.error!;
  }

  const stat = fs.statSync(resolved.filePath);
  return new NextResponse(null, {
    status: 200,
    headers: {
      "Content-Type": "audio/mpeg",
      "Accept-Ranges": "bytes",
      "Content-Length": String(stat.size),
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const resolved = await resolvePartFile(id);
  if (resolved.error || !resolved.filePath) {
    return resolved.error!;
  }

  const filePath = resolved.filePath;
  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const rangeHeader = request.headers.get("range");

  if (rangeHeader) {
    const range = parseRangeHeader(rangeHeader, fileSize);
    if (!range) {
      return new NextResponse(null, {
        status: 416,
        headers: {
          "Content-Range": `bytes */${fileSize}`,
        },
      });
    }

    const { start, end } = range;
    const stream = fs.createReadStream(filePath, { start, end });
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: {
        "Content-Type": "audio/mpeg",
        "Accept-Ranges": "bytes",
        "Content-Length": String(end - start + 1),
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Cache-Control": "no-store",
      },
    });
  }

  const stream = fs.createReadStream(filePath);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    status: 200,
    headers: {
      "Content-Type": "audio/mpeg",
      "Accept-Ranges": "bytes",
      "Content-Length": String(fileSize),
      "Cache-Control": "no-store",
    },
  });
}
