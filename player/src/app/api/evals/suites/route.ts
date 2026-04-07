import { readFile } from "node:fs/promises";
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

async function countJsonlLines(path: string) {
  try {
    const text = await readFile(path, "utf-8");
    return text.split(/\r?\n/).filter((line) => line.trim()).length;
  } catch {
    return 0;
  }
}

export async function GET() {
  const items = await prisma.evalSuite.findMany({
    orderBy: { createdAt: "desc" },
  });
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const slug = asString(body.slug);
  const title = asString(body.title);
  const sourcePath = asString(body.sourcePath);

  if (!slug || !title || !sourcePath) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const explicitCaseCount = Number(body.caseCount);
  const caseCount = Number.isFinite(explicitCaseCount) && explicitCaseCount > 0 ? explicitCaseCount : await countJsonlLines(sourcePath);

  const suite = await prisma.evalSuite.create({
    data: {
      slug,
      title,
      sourcePath,
      description: asString(body.description) || null,
      caseCount,
      tagsJson: asString(body.tagsJson) || null,
      status: asString(body.status) || "active",
    },
  });

  return NextResponse.json(suite);
}
