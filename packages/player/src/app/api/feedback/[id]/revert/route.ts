import { NextRequest } from "next/server";
import { revertFeedbackService } from "@ququ/process";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const result = await revertFeedbackService({
    db: prisma,
    feedbackId: id,
  });
  return serviceJson(result, { noStore: true });
}
