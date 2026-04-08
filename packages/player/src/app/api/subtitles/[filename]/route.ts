import { NextRequest } from "next/server";
import { getAudioSubtitleSegmentsService } from "@ququ/process";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ filename: string }> }
) {
  const { filename } = await params;
  const result = await getAudioSubtitleSegmentsService({
    db: prisma,
    audioFilename: decodeURIComponent(filename),
  });
  return serviceJson(result, { noStore: true });
}
