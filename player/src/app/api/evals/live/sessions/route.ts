import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

export async function GET(request: NextRequest) {
  const modelDeploymentId = request.nextUrl.searchParams.get("modelDeploymentId") || undefined;
  const items = await prisma.liveSession.findMany({
    where: modelDeploymentId ? { modelDeploymentId } : undefined,
    orderBy: { updatedAt: "desc" },
    take: 30,
    include: {
      inferHost: true,
      modelDeployment: true,
      turns: { orderBy: { createdAt: "asc" } },
    },
  });
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const modelDeploymentId = asString(body.modelDeploymentId);

  if (modelDeploymentId.length === 0) {
    return NextResponse.json({ error: "modelDeploymentId is required" }, { status: 400 });
  }

  const deployment = await prisma.modelDeployment.findUnique({
    where: { id: modelDeploymentId },
    include: { inferHost: true },
  });

  if (
    deployment === null ||
    deployment === undefined ||
    deployment.inferHost === null ||
    deployment.inferHost === undefined
  ) {
    return NextResponse.json({ error: "Deployment not found" }, { status: 404 });
  }

  const title = asString(body.title) || deployment.name + " live " + new Date().toISOString().slice(0, 19);
  const session = await prisma.liveSession.create({
    data: {
      inferHostId: deployment.inferHostId,
      modelDeploymentId: deployment.id,
      title,
      status: "active",
      scenario: asString(body.scenario) || null,
      notes: asString(body.notes) || null,
      transcriptJson: "[]",
    },
    include: {
      inferHost: true,
      modelDeployment: true,
      turns: { orderBy: { createdAt: "asc" } },
    },
  });

  return NextResponse.json({ session });
}
