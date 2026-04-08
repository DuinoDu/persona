import { NextRequest } from "next/server";
import { runLiveSessionChatService } from "@ququ/agent";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await runLiveSessionChatService({
    db: prisma,
    sessionId: id,
    body,
  });
  return serviceJson(result);
}
