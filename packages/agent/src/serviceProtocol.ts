import {
  toRemoteGenerationBody,
  type GenerationConfig,
  type PersonaMessage,
} from "./personaRuntime";

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asNumberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asArray(value: unknown) {
  return Array.isArray(value) ? value : [];
}

function normalizeOpenAiContent(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (!Array.isArray(value)) {
    return "";
  }
  return value
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      const record = asRecord(item);
      if (record === null) {
        return "";
      }
      if (typeof record.text === "string") {
        return record.text;
      }
      const nested = asRecord(record.text);
      if (nested && typeof nested.value === "string") {
        return nested.value;
      }
      return "";
    })
    .filter((item) => item.length > 0)
    .join("");
}

function normalizeLegacyResult(response: unknown, latencyMs: number) {
  const record = asRecord(response) ?? {};
  const outputText = asString(record.output_text).trim() || asString(record.raw_output_text).trim();
  const nextLatencyMs = asNumberOrNull(record.latency_ms) ?? latencyMs;
  const generatedTokens = asNumberOrNull(record.generated_tokens);
  const promptTokens = asNumberOrNull(record.prompt_tokens);

  return {
    outputText,
    result: {
      ...record,
      output_text: outputText,
      raw_output_text: asString(record.raw_output_text).trim() || outputText,
      latency_ms: nextLatencyMs,
      generated_tokens: generatedTokens,
      prompt_tokens: promptTokens,
    } as Record<string, unknown>,
  };
}

export function isVllmOpenAiRunner(runnerKind: string | null | undefined) {
  return runnerKind === "vllm_openai";
}

export function defaultServicePathsForRunner(runnerKind: string | null | undefined) {
  if (isVllmOpenAiRunner(runnerKind)) {
    return {
      chatPath: "/v1/chat/completions",
      streamPath: "/v1/chat/completions",
    };
  }
  return {
    chatPath: "/chat",
    streamPath: "/stream",
  };
}

export function buildServiceInferenceBody(input: {
  runnerKind: string | null | undefined;
  deploymentId: string;
  slug: string;
  baseModelPath: string;
  adapterPath?: string | null;
  messages: PersonaMessage[];
  generation: GenerationConfig;
  stream?: boolean;
}) {
  if (isVllmOpenAiRunner(input.runnerKind)) {
    const baseModelName = `${input.slug || input.deploymentId || "model"}-base`;
    const model = input.adapterPath ? input.slug || input.deploymentId || "adapter" : baseModelName;
    const body: Record<string, unknown> = {
      model,
      messages: input.messages,
      max_tokens: input.generation.maxNewTokens,
      temperature: input.generation.doSample ? input.generation.temperature : 0,
      top_p: input.generation.doSample ? input.generation.topP : 1,
      stream: Boolean(input.stream),
      chat_template_kwargs: {
        enable_thinking: false,
      },
    };
    if (input.stream) {
      body.stream_options = { include_usage: true };
    }
    return body;
  }

  return {
    messages: input.messages,
    ...toRemoteGenerationBody(input.generation),
  };
}

export function normalizeServiceChatResult(input: {
  runnerKind: string | null | undefined;
  response: unknown;
  latencyMs: number;
}) {
  if (!isVllmOpenAiRunner(input.runnerKind)) {
    return normalizeLegacyResult(input.response, input.latencyMs);
  }

  const record = asRecord(input.response) ?? {};
  const choice = asRecord(asArray(record.choices)[0]);
  const message = asRecord(choice?.message);
  const usage = asRecord(record.usage);
  const outputText = normalizeOpenAiContent(message?.content).trim();

  return {
    outputText,
    result: {
      ...record,
      output_text: outputText,
      raw_output_text: outputText,
      latency_ms: input.latencyMs,
      generated_tokens: asNumberOrNull(usage?.completion_tokens),
      prompt_tokens: asNumberOrNull(usage?.prompt_tokens),
    } as Record<string, unknown>,
  };
}

export function parseVllmStreamPayload(payload: Record<string, unknown>) {
  const usage = asRecord(payload.usage);
  const choice = asRecord(asArray(payload.choices)[0]);
  const delta = asRecord(choice?.delta);
  const errorText =
    asString(payload.error).trim() ||
    asString(asRecord(payload.error)?.message).trim() ||
    asString(asRecord(payload.detail)?.error).trim();

  return {
    done: payload.__sse_done === true,
    deltaText: normalizeOpenAiContent(delta?.content),
    finishReason: asString(choice?.finish_reason).trim() || null,
    promptTokens: asNumberOrNull(usage?.prompt_tokens),
    completionTokens: asNumberOrNull(usage?.completion_tokens),
    errorText: errorText.length > 0 ? errorText : null,
  };
}

export function buildVllmDonePayload(input: {
  outputText: string;
  latencyMs: number;
  promptTokens?: number | null;
  completionTokens?: number | null;
}) {
  return {
    type: "done",
    output_text: input.outputText,
    raw_output_text: input.outputText,
    latency_ms: input.latencyMs,
    prompt_tokens: input.promptTokens ?? null,
    generated_tokens: input.completionTokens ?? null,
    usage: {
      prompt_tokens: input.promptTokens ?? null,
      completion_tokens: input.completionTokens ?? null,
    },
  } satisfies Record<string, unknown>;
}
