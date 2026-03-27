import fs from "fs";
import { NextRequest, NextResponse } from "next/server";
import { getPartById } from "@/lib/partIndex";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

interface PartSentence {
  speaker_id?: string;
  speaker_name?: string;
  start: number;
  end: number;
  text: string;
}

interface LegacySegment {
  speaker?: string;
  start: number;
  end: number;
  text: string;
}

interface PartSegment {
  start: number;
  end: number;
  text: string;
  role: string;
  sourceKind: "sentences" | "segments";
  sourcePath: string;
  sourceIndex: number;
  absStart: number;
  absEnd: number;
  repair: {
    isRepaired: boolean;
    processedAt: string | null;
    feedbackId: string;
    operation: string | null;
  } | null;
}

interface SegmentRepairInfo {
  isRepaired: boolean;
  processedAt: string | null;
  feedbackId: string;
  operation: string | null;
}

function jsonNoStore(body: unknown, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}

function toSentenceRole(sentence: PartSentence) {
  if (sentence.speaker_id === "host") return "host";
  if (sentence.speaker_id === "guest") return "guest";
  return sentence.speaker_name || sentence.speaker_id || "UNKNOWN";
}

function toLegacyRole(segment: LegacySegment) {
  const speaker = segment.speaker || "";
  if (speaker === "host" || speaker === "guest") return speaker;
  if (speaker === "SPEAKER_01") return "guest";
  return speaker ? "host" : "UNKNOWN";
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

async function loadRepairMap(sourcePath: string) {
  const feedbacks = await prisma.feedback.findMany({
    where: {
      subtitleSourcePath: sourcePath,
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

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const part = getPartById(id);
  if (!part) {
    return jsonNoStore({ error: "Part not found" }, 404);
  }

  try {
    const [content, repairMap] = await Promise.all([
      Promise.resolve(
        JSON.parse(fs.readFileSync(part.partJsonPath, "utf-8")) as {
          meta?: { start?: number };
          sentences?: PartSentence[];
          segments?: LegacySegment[];
        }
      ),
      loadRepairMap(part.partJsonPath),
    ]);
    const clipStart = content.meta?.start ?? part.startSec;

    const segments: PartSegment[] = Array.isArray(content.sentences) && content.sentences.length > 0
      ? content.sentences
          .filter((sentence) => sentence.text && sentence.text.trim())
          .map((sentence, index) => ({
            start: sentence.start - clipStart,
            end: sentence.end - clipStart,
            text: sentence.text,
            role: toSentenceRole(sentence),
            sourceKind: "sentences" as const,
            sourcePath: part.partJsonPath,
            sourceIndex: index,
            absStart: sentence.start,
            absEnd: sentence.end,
            repair:
              repairMap.get(buildRepairKey(part.partJsonPath, "sentences", index)) ?? null,
          }))
      : (content.segments ?? [])
          .filter((segment) => segment.text && segment.text.trim())
          .map((segment, index) => ({
            start: segment.start - clipStart,
            end: segment.end - clipStart,
            text: segment.text,
            role: toLegacyRole(segment),
            sourceKind: "segments" as const,
            sourcePath: part.partJsonPath,
            sourceIndex: index,
            absStart: segment.start,
            absEnd: segment.end,
            repair:
              repairMap.get(buildRepairKey(part.partJsonPath, "segments", index)) ?? null,
          }));

    return jsonNoStore({ segments });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonNoStore({ error: message }, 500);
  }
}
