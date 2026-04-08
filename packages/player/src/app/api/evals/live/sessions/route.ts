import { NextRequest } from "next/server";
import { createLiveSessionService, listLiveSessionsService } from "@ququ/agent";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const result = await listLiveSessionsService({
    db: prisma,
    modelDeploymentId: request.nextUrl.searchParams.get("modelDeploymentId") || undefined,
  });
  return serviceJson(result);
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createLiveSessionService({ db: prisma, body });
  return serviceJson(result);
}
