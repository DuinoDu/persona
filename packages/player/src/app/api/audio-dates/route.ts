import { listAudioDatesService } from "@ququ/process";
import { serviceJson } from "@/lib/routeResponses";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = listAudioDatesService();
  return serviceJson(result, { noStore: true });
}
