import { NextResponse } from "next/server";
import { stopModelDeploymentService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await stopModelDeploymentService({
    db: prisma,
    deploymentId: id,
  });
  return NextResponse.json(result.body, { status: result.status });
}
