import { NextResponse } from "next/server";
import { downloadTrainingExportService } from "@ququ/agent";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await downloadTrainingExportService({
    db: prisma,
    exportId: id,
  });
  if (result.status !== 200 || "error" in result.body) {
    return NextResponse.json(result.body, { status: result.status });
  }

  const { body, filename, exportId } = result.body;
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Content-Disposition": `attachment; filename=\"${filename}\"`,
      "X-Export-Id": exportId,
    },
  });
}
