import { NextRequest, NextResponse } from "next/server";
import { createFeedbackService } from "@ququ/process";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await createFeedbackService({
    db: prisma,
    body,
  });
  return NextResponse.json(result.body, { status: result.status });
}
