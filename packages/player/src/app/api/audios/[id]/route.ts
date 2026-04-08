import { NextRequest, NextResponse } from "next/server";
import { updateAudioProgressService } from "@ququ/process";
import { prisma } from "@/lib/db";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const result = await updateAudioProgressService({
    db: prisma,
    audioId: id,
    body,
  });
  return NextResponse.json(result.body, { status: result.status });
}
