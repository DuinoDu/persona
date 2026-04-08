import { stableBlindLeftIsSlotA } from "@ququ/agent/evalArtifacts";
import { type AgentDbClient, asOptionalString, asString, jsonResult } from "./shared";

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

export async function createArenaJudgmentService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const leftRunRaw = asString(body.leftEvalRunId);
  const rightRunRaw = asString(body.rightEvalRunId);
  const caseId = asString(body.caseId);

  if (!leftRunRaw || !rightRunRaw || !caseId) {
    return jsonResult({ error: "leftEvalRunId / rightEvalRunId / caseId are required" }, 400);
  }
  if (leftRunRaw === rightRunRaw) {
    return jsonResult({ error: "leftEvalRunId and rightEvalRunId must be different" }, 400);
  }

  const [leftEvalRunId, rightEvalRunId] = canonicalPair(leftRunRaw, rightRunRaw);
  const winner = ALLOWED_WINNERS.has(asString(body.winner)) ? asString(body.winner) : "skip";
  const failureTagsRaw: unknown[] = Array.isArray(body.failureTags) ? body.failureTags : [];
  const failureTags = failureTagsRaw
    .map((item: unknown) => asString(item))
    .filter((item: string, index: number, items: string[]) => item.length > 0 && ALLOWED_FAILURE_TAGS.has(item) && items.indexOf(item) === index);

  const [leftRun, rightRun] = await Promise.all([
    input.db.evalRun.findUnique({ where: { id: leftEvalRunId } }),
    input.db.evalRun.findUnique({ where: { id: rightEvalRunId } }),
  ]);

  if (!leftRun || !rightRun) {
    return jsonResult({ error: "Run not found" }, 404);
  }
  if (leftRun.evalSuiteId && rightRun.evalSuiteId && leftRun.evalSuiteId !== rightRun.evalSuiteId) {
    return jsonResult({ error: "Runs belong to different suites" }, 400);
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

  const judgment = await input.db.arenaJudgment.upsert({
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

  return jsonResult({ judgment });
}
