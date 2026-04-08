import { PersonaInferenceRequest, RuntimeSignature } from "./personaRuntime";

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? Math.floor(value) : null;
}

function jsonString(value: unknown) {
  return value === undefined ? null : JSON.stringify(value ?? null);
}

export interface BuildLiveInferenceTraceInput {
  sourceType: string;
  sourceId: string;
  status?: string;
  inferHostId?: string | null;
  modelDeploymentId?: string | null;
  evalRunId?: string | null;
  liveSessionId?: string | null;
  liveTurnId?: string | null;
  promptVersionId?: string | null;
  generationConfigProfileId?: string | null;
  contextBuilderProfileId?: string | null;
  runtimeSignature: RuntimeSignature;
  request: PersonaInferenceRequest;
  trimReport?: unknown;
  summarySnapshot?: unknown;
  response?: unknown;
  outputText?: string | null;
  remoteLogPath?: string | null;
  remoteArtifactPath?: string | null;
  error?: string | null;
}

export function buildLiveInferenceTraceData(
  input: BuildLiveInferenceTraceInput
) {
  const responseRecord =
    typeof input.response === "object" && input.response !== null
      ? (input.response as Record<string, unknown>)
      : null;

  return {
    sourceType: input.sourceType,
    sourceId: input.sourceId,
    status: input.status || "succeeded",
    inferHostId: input.inferHostId ?? null,
    modelDeploymentId: input.modelDeploymentId ?? null,
    evalRunId: input.evalRunId ?? null,
    liveSessionId: input.liveSessionId ?? null,
    liveTurnId: input.liveTurnId ?? null,
    promptVersionId: input.promptVersionId ?? null,
    generationConfigProfileId: input.generationConfigProfileId ?? null,
    contextBuilderProfileId: input.contextBuilderProfileId ?? null,
    caseId: null,
    runtimeSignatureJson: JSON.stringify(input.runtimeSignature),
    finalMessagesJson: JSON.stringify(input.request.messages),
    generationConfigJson: JSON.stringify(input.request.generation),
    traceMetaJson: jsonString(input.request.traceMeta),
    summarySnapshotJson: jsonString(input.summarySnapshot),
    trimReportJson: jsonString(input.trimReport),
    estimatedPromptTokens: asNumber((input.trimReport as Record<string, unknown> | null)?.finalEstimatedPromptTokens),
    generatedTokens: asNumber(responseRecord?.generated_tokens),
    readyWaitMs: asNumber(responseRecord?.ready_wait_ms),
    firstTokenLatencyMs: asNumber(responseRecord?.first_token_latency_ms),
    totalLatencyMs: asNumber(responseRecord?.latency_ms),
    outputText: (input.outputText ?? asString(responseRecord?.output_text)) || null,
    rawOutputJson: jsonString(input.response),
    remoteLogPath: input.remoteLogPath ?? null,
    remoteArtifactPath: (input.remoteArtifactPath ?? asString(responseRecord?.trace_path)) || null,
    error: input.error ?? null,
  };
}
