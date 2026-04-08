import { syncAudiosService } from "@ququ/process";
import { prisma } from "@/lib/db";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function POST() {
  const result = await syncAudiosService({ db: prisma });
  return serviceJson(result);
}
