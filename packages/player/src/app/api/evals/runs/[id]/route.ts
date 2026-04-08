import { NextRequest, NextResponse } from "next/server";
import { getEvalRunService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await getEvalRunService({
    db: prisma,
    runId: id,
    refresh: request.nextUrl.searchParams.get("refresh") === "1",
  });
  return NextResponse.json(result.body, { status: result.status });
}
