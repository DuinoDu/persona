import { Readable } from "stream";
import { NextRequest, NextResponse } from "next/server";
import { openPartAudioStreamService, resolvePartAudioStreamService } from "@ququ/process";

export const dynamic = "force-dynamic";

export async function HEAD(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await resolvePartAudioStreamService({ partId: id });
  if (result.status !== 200 || !result.body.filePath || !result.body.fileSize) {
    return NextResponse.json(result.body, { status: result.status });
  }

  return new NextResponse(null, {
    status: 200,
    headers: {
      "Content-Type": "audio/mpeg",
      "Accept-Ranges": "bytes",
      "Content-Length": String(result.body.fileSize),
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await openPartAudioStreamService({
    partId: id,
    rangeHeader: request.headers.get("range"),
  });
  if (!result.ok) {
    return NextResponse.json(result.body, {
      status: result.status,
      headers: result.body.contentRange
        ? {
            "Content-Range": result.body.contentRange,
          }
        : undefined,
    });
  }

  return new NextResponse(Readable.toWeb(result.stream) as ReadableStream, {
    status: result.status,
    headers: {
      "Content-Type": "audio/mpeg",
      "Accept-Ranges": "bytes",
      "Content-Length": String(result.contentLength),
      ...(result.contentRange
        ? {
            "Content-Range": result.contentRange,
          }
        : {}),
      "Cache-Control": "no-store",
    },
  });
}
