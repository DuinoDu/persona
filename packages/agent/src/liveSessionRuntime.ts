import { buildPersonaContext, type PersonaTurn } from "./personaContextBuilder";
import {
  buildPersonaInferenceRequest,
  buildRuntimeSignature,
  normalizeGenerationConfig,
  type PersonaMessage,
  type GenerationConfig,
} from "./personaRuntime";
import { buildLiveServiceArtifacts, defaultServicePortForSlug, type InferHostJobConfig } from "./remoteJobs";
import {
  buildServiceInferenceBody,
  defaultServicePathsForRunner,
} from "./serviceProtocol";

export interface LiveSessionLike {
  id: string;
  summaryText?: string | null;
}

export interface LiveDeploymentLike {
  id: string;
  slug: string;
  baseModelPath: string;
  adapterPath?: string | null;
  systemPromptFile?: string | null;
  runnerKind?: string | null;
  serviceMode?: string | null;
  serviceBaseUrl?: string | null;
  serviceChatPath?: string | null;
  serviceStreamPath?: string | null;
  contextBuilderConfigJson?: string | null;
}

export interface PrepareLiveSessionInferenceInput {
  session: LiveSessionLike;
  deployment: LiveDeploymentLike;
  inferHost: InferHostJobConfig;
  turns: PersonaTurn[];
  content: string;
  generation?: Partial<GenerationConfig> | null;
  source: string;
  systemPrompt?: string | null;
  summary?: string | null;
  extraContextMessages?: PersonaMessage[];
  maxInputTokens?: number | null;
  maxRecentTurns?: number | null;
  extraTraceMeta?: Record<string, unknown> | null;
}

export interface PreparedLiveSessionInference {
  content: string;
  port: number;
  artifacts: ReturnType<typeof buildLiveServiceArtifacts>;
  chatUrl: string;
  streamUrl: string;
  generation: GenerationConfig;
  context: ReturnType<typeof buildPersonaContext>;
  runtimeSignature: ReturnType<typeof buildRuntimeSignature>;
  requestEnvelope: ReturnType<typeof buildPersonaInferenceRequest>;
  hostConfig: InferHostJobConfig;
  inferenceBody: Record<string, unknown>;
  streamInferenceBody: Record<string, unknown>;
  conversationMessages: ReturnType<typeof buildPersonaContext>["messages"];
  contextSettings: {
    maxInputTokens: number;
    maxRecentTurns: number;
  };
}

export function readTrimmedString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

export function readNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function readBoolean(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value === "true" || value === "1" || value === "on";
  return false;
}

export function jsonStringOrNull(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }
  return JSON.stringify(value);
}

function parseJsonObject(value: string | null | undefined) {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value);
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function readPositiveInt(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
}

export function resolveLiveContextSettings(value: string | null | undefined) {
  const record = parseJsonObject(value);
  return {
    maxInputTokens: readPositiveInt(record?.maxInputTokens, 12000),
    maxRecentTurns: readPositiveInt(record?.maxRecentTurns, 8),
  };
}

export function resolveLiveServicePort(baseUrl: string | null | undefined, slug: string) {
  if (baseUrl) {
    try {
      const url = new URL(baseUrl);
      const parsed = Number(url.port);
      if (Number.isFinite(parsed) && parsed > 0) {
        return parsed;
      }
    } catch {
      // ignore malformed url and fall back to slug-derived port
    }
  }
  return defaultServicePortForSlug(slug);
}

export function parseRequestedGeneration(value: Record<string, unknown> | null | undefined) {
  const body = value ?? {};
  return normalizeGenerationConfig({
    maxNewTokens: readNumber(body.maxNewTokens, 256),
    doSample: readBoolean(body.doSample),
    temperature: readNumber(body.temperature, 0.7),
    topP: readNumber(body.topP, 0.95),
  });
}

export function prepareLiveSessionInference(
  input: PrepareLiveSessionInferenceInput
): PreparedLiveSessionInference {
  const content = readTrimmedString(input.content);
  const generation = normalizeGenerationConfig(input.generation);
  const contextSettings = resolveLiveContextSettings(input.deployment.contextBuilderConfigJson);
  const port = resolveLiveServicePort(input.deployment.serviceBaseUrl, input.deployment.slug);
  const artifacts = buildLiveServiceArtifacts(
    input.inferHost.workspacePath,
    input.deployment.slug,
    port
  );
  const servicePaths = defaultServicePathsForRunner(input.deployment.runnerKind);
  const chatUrl = artifacts.baseUrl + (input.deployment.serviceChatPath || servicePaths.chatPath);
  const streamUrl = artifacts.baseUrl + (input.deployment.serviceStreamPath || servicePaths.streamPath);
  const context = buildPersonaContext({
    turns: input.turns,
    nextUserMessage: content,
    systemPrompt: input.systemPrompt ?? null,
    summary: input.summary ?? input.session.summaryText ?? null,
    extraMessages: input.extraContextMessages ?? [],
    maxInputTokens: input.maxInputTokens ?? contextSettings.maxInputTokens,
    reserveOutputTokens: generation.maxNewTokens,
    maxRecentTurns: input.maxRecentTurns ?? contextSettings.maxRecentTurns,
  });
  const runtimeSignature = buildRuntimeSignature({
    deploymentId: input.deployment.id,
    baseModelPath: input.deployment.baseModelPath,
    adapterPath: input.deployment.adapterPath ?? null,
    promptVersion: input.deployment.systemPromptFile ?? null,
    generationConfigVersion: "live_default_v1",
    contextBuilderVersion: String(
      context.trimReport.contextBuilderVersion || "persona_context_builder_v1"
    ),
    runnerKind: input.deployment.runnerKind || "unknown",
    serviceMode: input.deployment.serviceMode || "unknown",
  });
  const requestEnvelope = buildPersonaInferenceRequest({
    runtimeSignature,
    messages: context.messages,
    generation,
    traceMeta: {
      source: input.source,
      sessionId: input.session.id,
      deploymentId: input.deployment.id,
      stableTurnIds: context.stableTurnIds,
      orphanTurnIds: context.orphanTurnIds,
      trimReport: context.trimReport,
      ...(input.extraTraceMeta ?? {}),
    },
  });
  const hostConfig: InferHostJobConfig = {
    sshHost: input.inferHost.sshHost,
    sshPort: input.inferHost.sshPort,
    sshUser: input.inferHost.sshUser,
    workspacePath: input.inferHost.workspacePath,
  };
  const inferenceBody = buildServiceInferenceBody({
    runnerKind: input.deployment.runnerKind,
    deploymentId: input.deployment.id,
    slug: input.deployment.slug,
    baseModelPath: input.deployment.baseModelPath,
    adapterPath: input.deployment.adapterPath ?? null,
    messages: requestEnvelope.messages,
    generation: requestEnvelope.generation,
    stream: false,
  });
  const streamInferenceBody = buildServiceInferenceBody({
    runnerKind: input.deployment.runnerKind,
    deploymentId: input.deployment.id,
    slug: input.deployment.slug,
    baseModelPath: input.deployment.baseModelPath,
    adapterPath: input.deployment.adapterPath ?? null,
    messages: requestEnvelope.messages,
    generation: requestEnvelope.generation,
    stream: true,
  });

  return {
    content,
    port,
    artifacts,
    chatUrl,
    streamUrl,
    generation,
    context,
    runtimeSignature,
    requestEnvelope,
    hostConfig,
    inferenceBody,
    streamInferenceBody,
    conversationMessages: context.messages.filter((message) => message.role !== "system"),
    contextSettings,
  };
}
