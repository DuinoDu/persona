import { NextRequest } from "next/server";
import { listAudiosService } from "@ququ/process";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

const MAX_LIMIT = 50;
const DEFAULT_LIMIT = 10;
const SINGLE_AUDIO_ID = "single-audio";

export const dynamic = "force-dynamic";

void MAX_LIMIT;
void DEFAULT_LIMIT;
void SINGLE_AUDIO_ID;

export async function GET(request: NextRequest) {
  const result = await listAudiosService({
    db: prisma,
    requestUrl: request.url,
  });
  return serviceJson(result, { noStore: true });
}
