import { NextRequest } from "next/server";
import { getPartSubtitleSegmentsService } from "@ququ/process";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await getPartSubtitleSegmentsService({
    db: prisma,
    partId: id,
  });
  return serviceJson(result, { noStore: true });
}
