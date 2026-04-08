import { getPartById } from "../partIndex";
import {
  resolveSubtitleSegmentsForAudio,
  resolveSubtitleSegmentsForPartId,
} from "../subtitleSegments";
import { type JsonServiceResult, jsonResult, type ProcessDbClient } from "./shared";

export interface SegmentRepairInfo {
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

function mergeFeedbackPatch(
  repairMap: Map<string, SegmentRepairInfo>,
  feedback: {
    id: string;
    processedAt: Date | null;
    repairPatchJson: string | null;
    subtitleSourcePath: string | null;
    subtitleSourceKind: string | null;
    subtitleSourceIndex: number | null;
  }
) {
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
      return;
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

async function loadRepairMapByWhere(
  db: ProcessDbClient,
  where: Record<string, unknown>
) {
  const feedbacks = await db.feedback.findMany({
    where: {
      ...where,
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
    mergeFeedbackPatch(repairMap, feedback);
  }
  return repairMap;
}

export async function loadRepairMapByAudioFilename(db: ProcessDbClient, audioFilename: string) {
  return loadRepairMapByWhere(db, { audioFilename });
}

export async function loadRepairMapBySourcePath(db: ProcessDbClient, sourcePath: string) {
  return loadRepairMapByWhere(db, { subtitleSourcePath: sourcePath });
}

function enrichSegmentsWithRepair<T extends { sourcePath: string; sourceKind: string; sourceIndex: number }>(
  segments: T[],
  repairMap: Map<string, SegmentRepairInfo>
) {
  return segments.map((segment) => ({
    ...segment,
    repair:
      repairMap.get(buildRepairKey(segment.sourcePath, segment.sourceKind, segment.sourceIndex)) ?? null,
  }));
}

export async function getAudioSubtitleSegmentsService(input: {
  db: ProcessDbClient;
  audioFilename: string;
}): Promise<JsonServiceResult<{ segments?: unknown[]; error?: string }>> {
  try {
    const [segments, repairMap] = await Promise.all([
      Promise.resolve(resolveSubtitleSegmentsForAudio(input.audioFilename)),
      loadRepairMapByAudioFilename(input.db, input.audioFilename),
    ]);
    return jsonResult({ segments: enrichSegmentsWithRepair(segments, repairMap) });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: message }, message === "Subtitle not found" ? 404 : 500);
  }
}

export async function getPartSubtitleSegmentsService(input: {
  db: ProcessDbClient;
  partId: string;
}): Promise<JsonServiceResult<{ segments?: unknown[]; error?: string }>> {
  const part = getPartById(input.partId);
  if (!part) {
    return jsonResult({ error: "Part not found" }, 404);
  }

  try {
    const [segments, repairMap] = await Promise.all([
      Promise.resolve(resolveSubtitleSegmentsForPartId(input.partId)),
      loadRepairMapBySourcePath(input.db, part.partJsonPath),
    ]);
    return jsonResult({ segments: enrichSegmentsWithRepair(segments, repairMap) });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: message }, message === "Subtitle not found" ? 404 : 500);
  }
}
