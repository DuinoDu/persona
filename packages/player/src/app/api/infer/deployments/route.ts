import { NextRequest, NextResponse } from "next/server";
import { createModelDeploymentService, listModelDeploymentsService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await listModelDeploymentsService({ db: prisma });
  return NextResponse.json(result.body, { status: result.status });
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createModelDeploymentService({
    db: prisma,
    body,
  });
  return NextResponse.json(result.body, { status: result.status });
}
