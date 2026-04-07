import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { stableBlindLeftIsSlotA } from "@/lib/evalArtifacts";

export const dynamic = "force-dynamic";

const ALLOWED_WINNERS = new Set(["A", "B", "tie", "skip"]);
const ALLOWED_FAILURE_TAGS = new Set([
  "too_short",
  "style_drift",
  "no_premise_fix",
  "vague_comfort",
  "too_harsh",
  "multi_turn_drift",
  "leakage",
]);

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asOptionalString(value: unknown) {
  const normalized = asString(value);
  return normalized.length > 0 ? normalized : null;
}

function asScore(value: unknown) {
  const normalized = asString(value);
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  const intValue = Math.trunc(parsed);
  if (intValue < 1 || intValue > 5) {
    return null;
  }
  return intValue;
}

function canonicalPair(leftRunId: string, rightRunId: string) {
  return leftRunId.localeCompare(rightRunId) <= 0 ? [leftRunId, rightRunId] : [rightRunId, leftRunId];
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const leftRunRaw = asString(body.leftEvalRunId);
  const rightRunRaw = asString(body.rightEvalRunId);
  const caseId = asString(body.caseId);

  if (!leftRunRaw || !rightRunRaw || !caseId) {
    return NextResponse.json({ error: "leftEvalRunId / rightEvalRunId / caseId are required" }, { status: 400 });
  }
  if (leftRunRaw === rightRunRaw) {
    return NextResponse.json({ error: "leftEvalRunId and rightEvalRunId must be different" }, { status: 400 });
  }

  const [leftEvalRunId, rightEvalRunId] = canonicalPair(leftRunRaw, rightRunRaw);
  const winner = ALLOWED_WINNERS.has(asString(body.winner)) ? asString(body.winner) : "skip";
  const failureTagsRaw: unknown[] = Array.isArray(body.failureTags) ? body.failureTags : [];
  const failureTags = failureTagsRaw
    .map((item: unknown) => asString(item))
    .filter((item: string, index: number, items: string[]) => item.length > 0 && ALLOWED_FAILURE_TAGS.has(item) && items.indexOf(item) === index);

  const [leftRun, rightRun] = await Promise.all([
    prisma.evalRun.findUnique({ where: { id: leftEvalRunId } }),
    prisma.evalRun.findUnique({ where: { id: rightEvalRunId } }),
  ]);

  if (!leftRun || !rightRun) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }
  if (leftRun.evalSuiteId && rightRun.evalSuiteId && leftRun.evalSuiteId !== rightRun.evalSuiteId) {
    return NextResponse.json({ error: "Runs belong to different suites" }, { status: 400 });
  }

  const evalSuiteId = asOptionalString(body.evalSuiteId) || leftRun.evalSuiteId || rightRun.evalSuiteId || null;
  const caseSlice = asOptionalString(body.caseSlice);
  const promptPreview = asOptionalString(body.promptPreview);
  const leftIsSlotA = stableBlindLeftIsSlotA(leftEvalRunId, rightEvalRunId, caseId);

  let winnerEvalRunId: string | null = null;
  if (winner === "A") {
    winnerEvalRunId = leftIsSlotA ? leftEvalRunId : rightEvalRunId;
  } else if (winner === "B") {
    winnerEvalRunId = leftIsSlotA ? rightEvalRunId : leftEvalRunId;
  }

  const judgment = await prisma.arenaJudgment.upsert({
    where: {
      leftEvalRunId_rightEvalRunId_caseId: {
        leftEvalRunId,
        rightEvalRunId,
        caseId,
      },
    },
    update: {
      evalSuiteId,
      caseSlice,
      promptPreview,
      winner,
      winnerEvalRunId,
      personaScore: asScore(body.personaScore),
      judgmentScore: asScore(body.judgmentScore),
      premiseScore: asScore(body.premiseScore),
      structureScore: asScore(body.structureScore),
      actionabilityScore: asScore(body.actionabilityScore),
      naturalnessScore: asScore(body.naturalnessScore),
      stabilityScore: asScore(body.stabilityScore),
      failureTagsJson: failureTags.length > 0 ? JSON.stringify(failureTags) : null,
      notes: asOptionalString(body.notes),
    },
    create: {
      evalSuiteId,
      leftEvalRunId,
      rightEvalRunId,
      caseId,
      caseSlice,
      promptPreview,
      winner,
      winnerEvalRunId,
      personaScore: asScore(body.personaScore),
      judgmentScore: asScore(body.judgmentScore),
      premiseScore: asScore(body.premiseScore),
      structureScore: asScore(body.structureScore),
      actionabilityScore: asScore(body.actionabilityScore),
      naturalnessScore: asScore(body.naturalnessScore),
      stabilityScore: asScore(body.stabilityScore),
      failureTagsJson: failureTags.length > 0 ? JSON.stringify(failureTags) : null,
      notes: asOptionalString(body.notes),
    },
  });

  return NextResponse.json({ judgment });
}
