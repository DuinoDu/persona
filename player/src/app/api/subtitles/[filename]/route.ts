import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { resolveSubtitleSegmentsForAudio } from "@/lib/subtitleSegments";

export const dynamic = "force-dynamic";

interface SegmentRepairInfo {
  isRepaired: boolean;
  processedAt: string | null;
  feedbackId: string;
  operation: string | null;
}

function buildRepairKey(sourcePath: string, sourceKind: string, sourceIndex: number) {
  return `${sourcePath}::${sourceKind}::${sourceIndex}`;
}

function applyRepairMark(
  repairMap: Map<string, SegmentRepairInfo>,
  sourcePath: string | null,
  sourceKind: string | null,
  sourceIndex: number | null,
  info: SegmentRepairInfo
) {
  if (!sourcePath || !sourceKind || typeof sourceIndex !== "number") {
    return;
  }

  const key = buildRepairKey(sourcePath, sourceKind, sourceIndex);
  const existing = repairMap.get(key);
  const existingTime = existing?.processedAt ? Date.parse(existing.processedAt) : 0;
  const incomingTime = info.processedAt ? Date.parse(info.processedAt) : 0;
  if (!existing || incomingTime >= existingTime) {
    repairMap.set(key, info);
  }
}

async function loadRepairMap(audioFilename: string) {
  const feedbacks = await prisma.feedback.findMany({
    where: {
      audioFilename,
      processingStatus: "已处理",
      repairStatus: "applied",
    },
    orderBy: { processedAt: "desc" },
    select: {
      id: true,
      processedAt: true,
      repairPatchJson: true,
      subtitleSourcePath: true,
      subtitleSourceKind: true,
      subtitleSourceIndex: true,
    },
  });

  const repairMap = new Map<string, SegmentRepairInfo>();
  for (const feedback of feedbacks) {
    const info: SegmentRepairInfo = {
      isRepaired: true,
      processedAt: feedback.processedAt?.toISOString() ?? null,
      feedbackId: feedback.id,
      operation: null,
    };

    if (feedback.repairPatchJson) {
      try {
        const patch = JSON.parse(feedback.repairPatchJson) as {
          operation?: string | null;
          sourcePath?: string | null;
          sourceKind?: string | null;
          changes?: Array<{ sourceIndex?: number | null }>;
        };
        info.operation = patch.operation ?? null;
        for (const change of patch.changes ?? []) {
          applyRepairMark(
            repairMap,
            patch.sourcePath ?? feedback.subtitleSourcePath,
            patch.sourceKind ?? feedback.subtitleSourceKind,
            typeof change.sourceIndex === "number" ? change.sourceIndex : null,
            info
          );
        }
        continue;
      } catch {
        // fall back to current segment mark
      }
    }

    applyRepairMark(
      repairMap,
      feedback.subtitleSourcePath,
      feedback.subtitleSourceKind,
      feedback.subtitleSourceIndex,
      info
    );
  }

  return repairMap;
}

function jsonNoStore(body: unknown, init?: { status?: number }) {
  return NextResponse.json(body, {
    status: init?.status,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ filename: string }> }
) {
  const { filename } = await params;
  const decodedFilename = decodeURIComponent(filename);

  try {
    const [segments, repairMap] = await Promise.all([
      Promise.resolve(resolveSubtitleSegmentsForAudio(decodedFilename)),
      loadRepairMap(decodedFilename),
    ]);
    const enrichedSegments = segments.map((segment) => {
      const repair = repairMap.get(
        buildRepairKey(segment.sourcePath, segment.sourceKind, segment.sourceIndex)
      );
      return {
        ...segment,
        repair: repair ?? null,
      };
    });
    return jsonNoStore({ segments: enrichedSegments });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message === "Subtitle not found") {
      return jsonNoStore({ error: message }, { status: 404 });
    }
    return jsonNoStore({ error: message }, { status: 500 });
  }
}
