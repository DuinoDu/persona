import { NextRequest } from "next/server";
import { startLiveSessionStreamService } from "@ququ/agent";
import { prisma } from "@/lib/db";
import { serviceJson, sseResponse } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await startLiveSessionStreamService({
    db: prisma,
    sessionId: id,
    body,
    signal: request.signal,
  });

  if (!("stream" in result)) {
    return serviceJson(result);
  }

  return sseResponse(result.stream);
}
