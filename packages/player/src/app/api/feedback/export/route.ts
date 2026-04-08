import { exportFeedbackCsvService } from "@ququ/process";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await exportFeedbackCsvService({ db: prisma });

  return new Response(result.csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${result.filename}"`,
    },
  });
}
