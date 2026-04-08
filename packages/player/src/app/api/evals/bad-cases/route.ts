import { NextRequest, NextResponse } from "next/server";
import { createBadCaseService, listBadCasesService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const result = await listBadCasesService({
    db: prisma,
    sourceType: url.searchParams.get("sourceType"),
    status: url.searchParams.get("status"),
    limit: Number(url.searchParams.get("limit") || "50"),
  });
  return NextResponse.json(result.body, { status: result.status });
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createBadCaseService({
    db: prisma,
    body,
  });
  return NextResponse.json(result.body, { status: result.status });
}
