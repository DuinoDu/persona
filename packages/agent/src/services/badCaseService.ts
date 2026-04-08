import { type AgentDbClient, asOptionalString, asRecord, asString, asStringArray, jsonResult, parseJsonMaybe } from "./shared";

async function resolveInferenceTrace(db: AgentDbClient, input: {
  inferenceTraceId?: string | null;
  liveTurnId?: string | null;
  evalRunId?: string | null;
  caseId?: string | null;
}) {
  const include = {
    inferHost: true,
    modelDeployment: true,
    evalRun: true,
    liveSession: { include: { inferHost: true, modelDeployment: true } },
    liveTurn: true,
    promptVersion: true,
    generationConfigProfile: true,
    contextBuilderProfile: true,
  };

  if (input.inferenceTraceId) {
    return db.inferenceTrace.findUnique({
      where: { id: input.inferenceTraceId },
      include,
    });
  }

  if (input.liveTurnId) {
    return db.inferenceTrace.findFirst({
      where: { liveTurnId: input.liveTurnId },
      include,
      orderBy: { createdAt: "desc" },
    });
  }

  if (input.evalRunId && input.caseId) {
    return db.inferenceTrace.findFirst({
      where: {
        evalRunId: input.evalRunId,
        caseId: input.caseId,
      },
      include,
      orderBy: { createdAt: "desc" },
    });
  }

  return null;
}

export async function listBadCasesService(input: {
  db: AgentDbClient;
  sourceType?: string | null;
  status?: string | null;
  limit?: number;
}) {
  const limit = Number.isFinite(input.limit)
    ? Math.min(Math.max(Math.trunc(input.limit ?? 50), 1), 200)
    : 50;

  const items = await input.db.badCase.findMany({
    where: {
      ...(input.sourceType ? { sourceType: input.sourceType } : {}),
      ...(input.status ? { status: input.status } : {}),
    },
    orderBy: { createdAt: "desc" },
    take: limit,
    include: {
      inferHost: true,
      modelDeployment: true,
      evalRun: true,
      liveSession: { include: { inferHost: true, modelDeployment: true } },
      liveTurn: true,
      inferenceTrace: true,
    },
  });

  return jsonResult({
    items: items.map((item: Record<string, any>) => ({
      ...item,
      failureTagsJson: parseJsonMaybe(item.failureTagsJson),
      rubricScoresJson: parseJsonMaybe(item.rubricScoresJson),
    })),
  });
}

export async function createBadCaseService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const inferenceTraceId = asOptionalString(body.inferenceTraceId);
  const evalRunId = asOptionalString(body.evalRunId);
  const liveSessionId = asOptionalString(body.liveSessionId);
  const liveTurnId = asOptionalString(body.liveTurnId);
  const caseId = asOptionalString(body.caseId);

  const inferenceTrace = await resolveInferenceTrace(input.db, {
    inferenceTraceId,
    liveTurnId,
    evalRunId,
    caseId,
  });

  const sourceId =
    asOptionalString(body.sourceId) ||
    asOptionalString(inferenceTrace?.sourceId) ||
    liveTurnId ||
    (evalRunId && caseId ? `${evalRunId}:${caseId}` : null) ||
    caseId ||
    inferenceTraceId ||
    null;

  const failureTags = asStringArray(body.failureTags);
  const rubricScores = body.rubricScores && typeof body.rubricScores === "object" ? body.rubricScores : null;
  const resolvedSourceType =
    asOptionalString(body.sourceType) ||
    asOptionalString(inferenceTrace?.sourceType) ||
    (liveTurnId ? "live_turn" : "offline_case");

  const badCase = await input.db.badCase.create({
    data: {
      sourceType: resolvedSourceType,
      sourceId,
      inferHostId: asOptionalString(body.inferHostId) || inferenceTrace?.inferHostId || null,
      modelDeploymentId: asOptionalString(body.modelDeploymentId) || inferenceTrace?.modelDeploymentId || null,
      evalRunId: evalRunId || inferenceTrace?.evalRunId || null,
      liveSessionId: liveSessionId || inferenceTrace?.liveSessionId || null,
      liveTurnId: liveTurnId || inferenceTrace?.liveTurnId || null,
      inferenceTraceId: inferenceTraceId || inferenceTrace?.id || null,
      caseId,
      title: asOptionalString(body.title),
      status: asOptionalString(body.status) || "open",
      severity: asOptionalString(body.severity) || "medium",
      failureTagsJson: failureTags.length > 0 ? JSON.stringify(failureTags) : null,
      rubricScoresJson: rubricScores ? JSON.stringify(rubricScores) : null,
      editedTargetText: asOptionalString(body.editedTargetText),
      chosenText: asOptionalString(body.chosenText),
      rejectedText: asOptionalString(body.rejectedText),
      notes: asOptionalString(body.notes),
    },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalRun: true,
      liveSession: { include: { inferHost: true, modelDeployment: true } },
      liveTurn: true,
      inferenceTrace: true,
    },
  });

  return jsonResult({ badCase });
}
