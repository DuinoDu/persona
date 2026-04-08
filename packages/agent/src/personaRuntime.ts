import { createHash } from "node:crypto";

export type PersonaRole = "system" | "user" | "assistant";

export interface PersonaMessage {
  role: PersonaRole;
  content: string;
}

export interface GenerationConfig {
  maxNewTokens: number;
  doSample: boolean;
  temperature: number;
  topP: number;
}

export interface RuntimeSignature {
  deploymentId: string;
  baseModelPath: string;
  adapterPath: string | null;
  promptVersion: string | null;
  generationConfigVersion: string;
  contextBuilderVersion: string;
  runnerKind: string;
  serviceMode: string;
  signatureKey: string;
}

export interface PersonaInferenceRequest {
  runtimeSignature: RuntimeSignature;
  messages: PersonaMessage[];
  generation: GenerationConfig;
  traceMeta: Record<string, unknown> | null;
}

export const DEFAULT_GENERATION_CONFIG_VERSION = "persona_generation_v1";
export const DEFAULT_CONTEXT_BUILDER_VERSION = "persona_context_builder_v1";

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => stableValue(item));
  }

  const record = asRecord(value);
  if (record === null) {
    return value;
  }

  const next: Record<string, unknown> = {};
  for (const key of Object.keys(record).sort()) {
    next[key] = stableValue(record[key]);
  }
  return next;
}

function stableStringify(value: unknown) {
  return JSON.stringify(stableValue(value));
}

function normalizePositiveInt(value: unknown, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  const rounded = Math.floor(parsed);
  return rounded > 0 ? rounded : fallback;
}

function normalizeFiniteNumber(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

export function normalizeGenerationConfig(
  input: Partial<GenerationConfig> | null | undefined = {}
): GenerationConfig {
  const config = input ?? {};
  return {
    maxNewTokens: normalizePositiveInt(config.maxNewTokens, 256),
    doSample: Boolean(config.doSample),
    temperature: normalizeFiniteNumber(config.temperature, 0.7, 0, 10),
    topP: normalizeFiniteNumber(config.topP, 0.95, 0, 1),
  };
}

export function buildRuntimeSignature(input: {
  deploymentId: string;
  baseModelPath: string;
  adapterPath?: string | null;
  promptVersion?: string | null;
  generationConfigVersion?: string | null;
  contextBuilderVersion?: string | null;
  runnerKind?: string | null;
  serviceMode?: string | null;
}): RuntimeSignature {
  const normalized = {
    deploymentId: asString(input.deploymentId),
    baseModelPath: asString(input.baseModelPath),
    adapterPath: input.adapterPath ?? null,
    promptVersion: input.promptVersion ?? null,
    generationConfigVersion: input.generationConfigVersion || DEFAULT_GENERATION_CONFIG_VERSION,
    contextBuilderVersion: input.contextBuilderVersion || DEFAULT_CONTEXT_BUILDER_VERSION,
    runnerKind: input.runnerKind || "unknown",
    serviceMode: input.serviceMode || "unknown",
  };
  const signatureKey = createHash("sha256")
    .update(stableStringify(normalized))
    .digest("hex")
    .slice(0, 16);

  return {
    ...normalized,
    signatureKey,
  };
}

export function buildPersonaInferenceRequest(input: {
  runtimeSignature: RuntimeSignature;
  messages: PersonaMessage[];
  generation?: Partial<GenerationConfig> | null;
  traceMeta?: Record<string, unknown> | null;
}): PersonaInferenceRequest {
  return {
    runtimeSignature: input.runtimeSignature,
    messages: input.messages,
    generation: normalizeGenerationConfig(input.generation),
    traceMeta: input.traceMeta ?? null,
  };
}

export function toRemoteGenerationBody(generation: GenerationConfig) {
  return {
    max_new_tokens: generation.maxNewTokens,
    do_sample: generation.doSample,
    temperature: generation.temperature,
    top_p: generation.topP,
  };
}

export function buildPersonaTraceEnvelope(input: {
  sourceType: string;
  sourceId: string;
  runtimeSignature: RuntimeSignature;
  request: PersonaInferenceRequest;
  context: Record<string, unknown>;
  result?: unknown;
  outputText?: string | null;
  rawOutputText?: string | null;
  latencyMs?: number | null;
  generatedTokens?: number | null;
  remoteLogPath?: string | null;
  error?: string | null;
}) {
  return {
    sourceType: input.sourceType,
    sourceId: input.sourceId,
    runtimeSignature: input.runtimeSignature,
    request: input.request,
    context: input.context,
    result: input.result ?? null,
    outputText: input.outputText ?? null,
    rawOutputText: input.rawOutputText ?? null,
    latencyMs: input.latencyMs ?? null,
    generatedTokens: input.generatedTokens ?? null,
    remoteLogPath: input.remoteLogPath ?? null,
    error: input.error ?? null,
  };
}
