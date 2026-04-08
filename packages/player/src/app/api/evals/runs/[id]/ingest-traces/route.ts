import { NextRequest, NextResponse } from "next/server";
import { ingestEvalRunTracesService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await ingestEvalRunTracesService({
    db: prisma,
    runId: id,
    body,
  });
  return NextResponse.json(result.body, { status: result.status });
}
