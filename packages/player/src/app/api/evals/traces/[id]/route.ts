import { NextRequest, NextResponse } from "next/server";
import { getEvalTraceService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await getEvalTraceService({
    db: prisma,
    traceViewerId: id,
  });
  return NextResponse.json(result.body, { status: result.status });
}
