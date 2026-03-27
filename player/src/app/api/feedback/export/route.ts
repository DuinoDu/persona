import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function escapeCsvValue(value: unknown) {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export async function GET() {
  const feedbacks = await prisma.feedback.findMany({
    orderBy: { createdAt: "desc" },
  });

  const headers = [
    "id",
    "createdAt",
    "audioId",
    "audioFilename",
    "audioDate",
    "audioPersonTag",
    "audioStartTime",
    "audioEndTime",
    "subtitleFile",
    "subtitleIndex",
    "subtitleStart",
    "subtitleEnd",
    "subtitleText",
    "subtitleSourceKind",
    "subtitleSourcePath",
    "subtitleSourceIndex",
    "subtitleAbsStart",
    "subtitleAbsEnd",
    "message",
    "processingStatus",
    "processedAt",
    "repairStatus",
    "repairSummary",
    "repairConfidence",
    "repairedText",
    "repairPatchJson",
    "repairError",
    "repairedAt",
  ];

  const rows = feedbacks.map((item) => [
    item.id,
    item.createdAt.toISOString(),
    item.audioId,
    item.audioFilename,
    item.audioDate,
    item.audioPersonTag,
    item.audioStartTime,
    item.audioEndTime,
    item.subtitleFile,
    item.subtitleIndex,
    item.subtitleStart,
    item.subtitleEnd,
    item.subtitleText,
    item.subtitleSourceKind,
    item.subtitleSourcePath,
    item.subtitleSourceIndex,
    item.subtitleAbsStart,
    item.subtitleAbsEnd,
    item.message,
    item.processingStatus,
    item.processedAt?.toISOString(),
    item.repairStatus,
    item.repairSummary,
    item.repairConfidence,
    item.repairedText,
    item.repairPatchJson,
    item.repairError,
    item.repairedAt?.toISOString(),
  ]);

  const csv = `\uFEFF${[headers, ...rows]
    .map((row) => row.map(escapeCsvValue).join(","))
    .join("\n")}`;

  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="feedback-export.csv"',
    },
  });
}
