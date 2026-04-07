import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asOptionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asPort(value: unknown) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 22;
}

export async function GET() {
  const items = await prisma.inferHost.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      _count: {
        select: {
          deployments: true,
          evalRuns: true,
          liveSessions: true,
        },
      },
    },
  });
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const name = asString(body.name);
  const sshHost = asString(body.sshHost);
  const sshUser = asString(body.sshUser);
  const workspacePath = asString(body.workspacePath);

  if (!name || !sshHost || !sshUser || !workspacePath) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const host = await prisma.inferHost.create({
    data: {
      name,
      sshHost,
      sshPort: asPort(body.sshPort),
      sshUser,
      workspacePath,
      gpuPolicy: asString(body.gpuPolicy) || "shared_service",
      status: asString(body.status) || "active",
      notes: asOptionalString(body.notes),
    },
  });

  return NextResponse.json(host);
}
