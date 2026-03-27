import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { resolveFeedbackTargetForAudio } from "@/lib/subtitleSegments";

export const dynamic = "force-dynamic";
const PROMPT_VERSION = "2026-03-25.v2";

function asTrimmedString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asOptionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asOptionalInt(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function asOptionalNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const audioFilename = asTrimmedString(body.audioFilename);
  const subtitleId = asTrimmedString(body.subtitleId);
  const submittedSubtitleFile = asTrimmedString(body.subtitleFile);
  const message = asTrimmedString(body.message);
  const subtitleText = asTrimmedString(body.subtitleText);
  const subtitleIndex = asOptionalInt(body.subtitleIndex);
  const subtitleStart = asOptionalNumber(body.subtitleStart);
  const subtitleEnd = asOptionalNumber(body.subtitleEnd);

  if (!subtitleText || !audioFilename || !message) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  let resolvedTarget;
  try {
    resolvedTarget = resolveFeedbackTargetForAudio({
      audioFilename,
      subtitleId,
      subtitleIndex,
      subtitleText,
      subtitleStart,
      subtitleEnd,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: message }, { status: 400 });
  }

  const subtitleFile = submittedSubtitleFile || audioFilename.replace(/\.mp3$/i, ".json");
  const result = await prisma.$transaction(async (tx) => {
    const feedback = await tx.feedback.create({
      data: {
        audioId: asOptionalString(body.audioId),
        audioFilename,
        audioDate: asOptionalString(body.audioDate),
        audioPersonTag: asOptionalString(body.audioPersonTag),
        audioStartTime: asOptionalString(body.audioStartTime),
        audioEndTime: asOptionalString(body.audioEndTime),
        subtitleFile,
        subtitleIndex,
        subtitleStart: resolvedTarget.start,
        subtitleEnd: resolvedTarget.end,
        subtitleText: resolvedTarget.text,
        subtitleSourceKind: resolvedTarget.sourceKind,
        subtitleSourcePath: resolvedTarget.sourcePath,
        subtitleSourceIndex: resolvedTarget.sourceIndex,
        subtitleAbsStart: resolvedTarget.absStart,
        subtitleAbsEnd: resolvedTarget.absEnd,
        message,
        processingStatus: "待处理",
        repairStatus: "pending",
      },
    });

    const job = await tx.feedbackRepairJob.create({
      data: {
        feedbackId: feedback.id,
        status: "pending",
        promptVersion: PROMPT_VERSION,
      },
    });

    return { feedback, job };
  });

  return NextResponse.json(result);
}
