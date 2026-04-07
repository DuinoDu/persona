import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asOptionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export async function GET() {
  const items = await prisma.modelDeployment.findMany({
    orderBy: { createdAt: "desc" },
    include: { inferHost: true },
  });
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const inferHostId = asString(body.inferHostId);
  const name = asString(body.name);
  const slug = asString(body.slug);
  const baseModelPath = asString(body.baseModelPath);

  if (!inferHostId || !name || !slug || !baseModelPath) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const deployment = await prisma.modelDeployment.create({
    data: {
      inferHostId,
      name,
      slug,
      baseModelPath,
      adapterPath: asOptionalString(body.adapterPath),
      systemPromptFile: asOptionalString(body.systemPromptFile),
      runnerKind: asString(body.runnerKind) || "batch_chat_eval",
      runnerScriptPath: asOptionalString(body.runnerScriptPath),
      serviceMode: asString(body.serviceMode) || "offline_only",
      serviceStatus: asString(body.serviceStatus) || "stopped",
      serviceBaseUrl: asOptionalString(body.serviceBaseUrl),
      serviceChatPath: asOptionalString(body.serviceChatPath),
      serviceStreamPath: asOptionalString(body.serviceStreamPath),
      defaultDevice: asString(body.defaultDevice) || "cuda",
      notes: asOptionalString(body.notes),
    },
  });

  return NextResponse.json(deployment);
}
