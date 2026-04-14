import { buildLiveInferenceTraceData } from "@ququ/agent/inferenceTrace";
import {
  jsonStringOrNull,
  parseRequestedGeneration,
  prepareLiveSessionInference,
  readTrimmedString,
} from "@ququ/agent/liveSessionRuntime";
import {
  buildPersonaSummaryText,
  parsePersonaMemoryState,
  seedPersonaMemoryState,
  updatePersonaMemoryState,
} from "../personaMemory";
import { runPersonaToolLoop } from "../personaToolLoop";
import { buildPersonaTraceEnvelope } from "@ququ/agent/personaRuntime";
import {
  buildRemoteHttpCommand,
  nextLiveServiceStatus,
  probeLiveService,
  remoteHttpJson,
  summarizeLiveServiceError,
  waitForLiveServiceReady,
} from "@ququ/agent/remoteJobs";
import { streamRemoteSseOverSsh } from "@ququ/agent/remoteSse";
import {
  buildVllmDonePayload,
  defaultServicePathsForRunner,
  isVllmOpenAiRunner,
  normalizeServiceChatResult,
  parseVllmStreamPayload,
} from "@ququ/agent/serviceProtocol";
import {
  asString,
  type AgentDbClient,
  jsonResult,
} from "./shared";

async function loadLiveSessionGraph(db: AgentDbClient, sessionId: string) {
  return db.liveSession.findUnique({
    where: { id: sessionId },
    include: {
      inferHost: true,
      modelDeployment: { include: { inferHost: true, contextBuilderProfile: true } },
      turns: { orderBy: { createdAt: "asc" } },
    },
  });
}

type LiveSessionContext =
  | {
      ok: false;
      error: ReturnType<typeof jsonResult>;
    }
  | {
      ok: true;
      session: any;
      deployment: any;
      inferHost: any;
    };

function resolveLiveSessionContext(session: any): LiveSessionContext {
  if (!session?.modelDeployment) {
    return { ok: false, error: jsonResult({ error: "Live session not found" }, 404) };
  }
  const deployment = session.modelDeployment;
  const inferHost = session.inferHost || deployment.inferHost;
  if (!inferHost) {
    return { ok: false, error: jsonResult({ error: "Infer host not found" }, 400) };
  }
  return {
    ok: true,
    session,
    deployment,
    inferHost,
  };
}

function buildPreparedLiveSessionInput(input: {
  session: any;
  deployment: any;
  inferHost: any;
  content: string;
  body: Record<string, unknown>;
  source: string;
}) {
  const memoryState = parsePersonaMemoryState(input.session.memoryStateJson);
  const toolLoop = runPersonaToolLoop({
    query: input.content,
    memoryState,
    turns: input.session.turns,
  });
  const prepared = prepareLiveSessionInference({
    session: input.session,
    deployment: {
      ...input.deployment,
      contextBuilderConfigJson: input.deployment.contextBuilderProfile?.configJson ?? null,
    },
    inferHost: input.inferHost,
    turns: input.session.turns,
    content: input.content,
    generation: parseRequestedGeneration(input.body),
    source: input.source,
    summary: buildPersonaSummaryText(memoryState) ?? input.session.summaryText ?? null,
    extraContextMessages: toolLoop.messages,
    extraTraceMeta: {
      toolLoop: {
        tools: toolLoop.plan.tools,
        reasons: toolLoop.plan.reasons,
        recallCounts: {
          profile: toolLoop.recall.profile.length,
          facts: toolLoop.recall.facts.length,
          openLoops: toolLoop.recall.openLoops.length,
          episodes: toolLoop.recall.episodes.length,
        },
      },
    },
  });

  return {
    prepared,
    toolLoop,
  };
}

async function persistLiveSessionSuccess(input: {
  db: AgentDbClient;
  session: any;
  deployment: any;
  inferHost: any;
  prepared: ReturnType<typeof prepareLiveSessionInference>;
  result: unknown;
  outputText: string;
  streaming: boolean;
}) {
  const transcript = input.prepared.conversationMessages.concat([
    { role: "assistant", content: input.outputText },
  ]);
  const payload =
    typeof input.result === "object" && input.result !== null
      ? (input.result as Record<string, unknown>)
      : {};
  const traceEnvelope = buildPersonaTraceEnvelope({
    sourceType: "live_session",
    sourceId: input.session.id,
    runtimeSignature: input.prepared.runtimeSignature,
    request: input.prepared.requestEnvelope,
    context: input.prepared.context.trimReport as Record<string, unknown>,
    result: input.result,
    outputText: input.outputText,
    rawOutputText: readTrimmedString(payload.raw_output_text),
    latencyMs: Number(payload.latency_ms) || 0,
    generatedTokens: Number(payload.generated_tokens) || 0,
    remoteLogPath: input.prepared.artifacts.logPath,
  });

  return input.db.$transaction(async (tx: AgentDbClient) => {
    if (input.prepared.context.orphanTurnIds.length > 0) {
      await tx.liveTurn.deleteMany({
        where: {
          id: { in: input.prepared.context.orphanTurnIds },
        },
      });
    }

    const createdUserTurn = await tx.liveTurn.create({
      data: {
        liveSessionId: input.session.id,
        role: "user",
        content: input.prepared.content,
      },
    });

    const createdAssistantTurn = await tx.liveTurn.create({
      data: {
        liveSessionId: input.session.id,
        role: "assistant",
        content: input.outputText,
        latencyMs: Number(payload.latency_ms) || 0,
        tokenCount: Number(payload.generated_tokens) || 0,
        rawJson: JSON.stringify(traceEnvelope),
      },
    });

    const inferenceTrace = await tx.inferenceTrace.create({
      data: buildLiveInferenceTraceData({
        sourceType: "live_turn",
        sourceId: createdAssistantTurn.id,
        inferHostId: input.inferHost.id,
        modelDeploymentId: input.deployment.id,
        liveSessionId: input.session.id,
        liveTurnId: createdAssistantTurn.id,
        promptVersionId: input.deployment.promptVersionId,
        generationConfigProfileId: input.deployment.generationConfigProfileId,
        contextBuilderProfileId: input.deployment.contextBuilderProfileId,
        runtimeSignature: input.prepared.runtimeSignature,
        request: input.prepared.requestEnvelope,
        trimReport: input.prepared.context.trimReport,
        summarySnapshot: input.session.summaryText,
        response: input.result,
        outputText: input.outputText,
        remoteLogPath: input.prepared.artifacts.logPath,
        remoteArtifactPath: readTrimmedString(payload.trace_path) || null,
      }),
    });
    const nextMemoryState = updatePersonaMemoryState({
      state: parsePersonaMemoryState(input.session.memoryStateJson),
      userText: input.prepared.content,
      assistantText: input.outputText,
      scenario: input.session.scenario,
      sourceTurnIds: [createdUserTurn.id, createdAssistantTurn.id],
      updatedAt: createdAssistantTurn.createdAt,
    });
    const nextSummaryText = buildPersonaSummaryText(nextMemoryState);
    const servicePaths = defaultServicePathsForRunner(input.deployment.runnerKind);

    const deploymentData = input.streaming
      ? {
          serviceStatus: "running_service",
          serviceBaseUrl: input.prepared.artifacts.baseUrl,
          serviceChatPath: input.deployment.serviceChatPath || servicePaths.chatPath,
          serviceStreamPath: input.deployment.serviceStreamPath || servicePaths.streamPath,
          serviceSessionName: input.prepared.artifacts.sessionName,
          serviceLogPath: input.prepared.artifacts.logPath,
          serviceStatusPath: input.prepared.artifacts.statusPath,
          serviceLastExitCode: null,
          serviceLastError: null,
          serviceLastHealthJson: null,
          serviceLastCheckedAt: new Date(),
        }
      : {
          serviceStatus: "running_service",
          serviceBaseUrl: input.prepared.artifacts.baseUrl,
          serviceChatPath: input.deployment.serviceChatPath || servicePaths.chatPath,
          serviceStreamPath: input.deployment.serviceStreamPath || servicePaths.streamPath,
          serviceSessionName: input.prepared.artifacts.sessionName,
          serviceLogPath: input.prepared.artifacts.logPath,
          serviceStatusPath: input.prepared.artifacts.statusPath,
          serviceLastExitCode: null,
          serviceLastError: null,
          serviceLastCheckedAt: new Date(),
        };

    const [updatedSession, updatedDeployment] = await Promise.all([
      tx.liveSession.update({
        where: { id: input.session.id },
        data: {
          status: "active",
          transcriptJson: JSON.stringify(transcript),
          summaryText: nextSummaryText,
          memoryStateJson: JSON.stringify(nextMemoryState),
          lastMemoryUpdatedAt: new Date(),
          notes: input.session.notes,
        },
        include: {
          inferHost: true,
          modelDeployment: { include: { inferHost: true, contextBuilderProfile: true } },
          turns: { orderBy: { createdAt: "asc" } },
        },
      }),
      tx.modelDeployment.update({
        where: { id: input.deployment.id },
        data: deploymentData,
        include: { inferHost: true },
      }),
    ]);

    return {
      userTurn: createdUserTurn,
      assistantTurn: createdAssistantTurn,
      inferenceTrace,
      updatedSession,
      updatedDeployment,
    };
  });
}

async function persistLiveSessionError(input: {
  db: AgentDbClient;
  session: any;
  deployment: any;
  prepared: ReturnType<typeof prepareLiveSessionInference>;
  message: string;
  streaming: boolean;
  stderrBuffer?: string;
}) {
  const probe = await probeLiveService({
    host: input.prepared.hostConfig,
    sessionName: input.prepared.artifacts.sessionName,
    statusPath: input.prepared.artifacts.statusPath,
    logPath: input.prepared.artifacts.logPath,
    baseUrl: input.prepared.artifacts.baseUrl,
  }).catch(() => null);

  const sessionNote = input.streaming ? "live_stream_error=" : "live_chat_error=";
  const servicePaths = defaultServicePathsForRunner(input.deployment.runnerKind);
  const deploymentData = input.streaming
    ? {
        serviceStatus: probe ? nextLiveServiceStatus(probe) : "failed",
        serviceBaseUrl: input.prepared.artifacts.baseUrl,
        serviceChatPath: input.deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: input.deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: input.prepared.artifacts.sessionName,
        serviceLogPath: input.prepared.artifacts.logPath,
        serviceStatusPath: input.prepared.artifacts.statusPath,
        serviceLastExitCode: probe?.exitCode ?? null,
        serviceLastError: [
          input.message,
          input.stderrBuffer?.trim(),
          probe ? summarizeLiveServiceError(probe) : null,
        ]
          .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index)
          .join(" | "),
        serviceLastHealthJson: jsonStringOrNull(probe?.healthJson),
        serviceLastCheckedAt: new Date(),
      }
    : {
        serviceStatus: probe ? nextLiveServiceStatus(probe) : "failed",
        serviceBaseUrl: input.prepared.artifacts.baseUrl,
        serviceChatPath: input.deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: input.deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: input.prepared.artifacts.sessionName,
        serviceLogPath: input.prepared.artifacts.logPath,
        serviceStatusPath: input.prepared.artifacts.statusPath,
        serviceLastExitCode: probe?.exitCode ?? null,
        serviceLastError: [input.message, probe ? summarizeLiveServiceError(probe) : null]
          .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index)
          .join(" | "),
        serviceLastHealthJson: jsonStringOrNull(probe?.healthJson),
        serviceLastCheckedAt: new Date(),
      };

  const [updatedSession, updatedDeployment] = await Promise.all([
    input.db.liveSession.update({
      where: { id: input.session.id },
      data: {
        status: "error",
        notes: [input.session.notes, sessionNote + input.message].filter(Boolean).join("\n"),
      },
      include: {
        inferHost: true,
        modelDeployment: { include: { inferHost: true, contextBuilderProfile: true } },
        turns: { orderBy: { createdAt: "asc" } },
      },
    }),
    input.db.modelDeployment.update({
      where: { id: input.deployment.id },
      data: deploymentData,
      include: { inferHost: true },
    }),
  ]);

  return {
    probe,
    updatedSession,
    updatedDeployment,
  };
}

export async function listLiveSessionsService(input: {
  db: AgentDbClient;
  modelDeploymentId?: string | null;
}) {
  const items = await input.db.liveSession.findMany({
    where: input.modelDeploymentId ? { modelDeploymentId: input.modelDeploymentId } : undefined,
    orderBy: { updatedAt: "desc" },
    take: 30,
    include: {
      inferHost: true,
      modelDeployment: { include: { inferHost: true, contextBuilderProfile: true } },
      turns: { orderBy: { createdAt: "asc" } },
    },
  });
  return jsonResult({ items });
}

export async function createLiveSessionService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const modelDeploymentId = asString(body.modelDeploymentId);

  if (modelDeploymentId.length === 0) {
    return jsonResult({ error: "modelDeploymentId is required" }, 400);
  }

  const deployment = await input.db.modelDeployment.findUnique({
    where: { id: modelDeploymentId },
    include: { inferHost: true, contextBuilderProfile: true },
  });

  if (!deployment?.inferHost) {
    return jsonResult({ error: "Deployment not found" }, 404);
  }

  const title = asString(body.title) || deployment.name + " live " + new Date().toISOString().slice(0, 19);
  const scenario = asString(body.scenario) || null;
  const seededMemoryState = seedPersonaMemoryState({ scenario });
  const session = await input.db.liveSession.create({
    data: {
      inferHostId: deployment.inferHostId,
      modelDeploymentId: deployment.id,
      title,
      status: "active",
      scenario,
      notes: asString(body.notes) || null,
      summaryText: buildPersonaSummaryText(seededMemoryState),
      memoryStateJson: JSON.stringify(seededMemoryState),
      lastMemoryUpdatedAt:
        seededMemoryState.profile.length > 0 ||
        seededMemoryState.facts.length > 0 ||
        seededMemoryState.openLoops.length > 0
          ? new Date()
          : null,
      transcriptJson: "[]",
    },
    include: {
      inferHost: true,
      modelDeployment: { include: { inferHost: true, contextBuilderProfile: true } },
      turns: { orderBy: { createdAt: "asc" } },
    },
  });

  return jsonResult({ session });
}

export async function runLiveSessionChatService(input: {
  db: AgentDbClient;
  sessionId: string;
  body?: Record<string, unknown> | null;
}) {
  const sessionGraph = await loadLiveSessionGraph(input.db, input.sessionId);
  const resolved = resolveLiveSessionContext(sessionGraph);
  if (!resolved.ok) {
    return resolved.error;
  }

  const body = input.body ?? {};
  const content = readTrimmedString(body.content);
  if (content.length === 0) {
    return jsonResult({ error: "content is required" }, 400);
  }

  const { prepared, toolLoop } = buildPreparedLiveSessionInput({
    session: resolved.session,
    deployment: resolved.deployment,
    inferHost: resolved.inferHost,
    content,
    body,
    source: "live_chat",
  });

  try {
    await waitForLiveServiceReady({
      host: prepared.hostConfig,
      sessionName: prepared.artifacts.sessionName,
      statusPath: prepared.artifacts.statusPath,
      logPath: prepared.artifacts.logPath,
      baseUrl: prepared.artifacts.baseUrl,
    });

    const startedAt = Date.now();
    const rawResult = await remoteHttpJson({
      host: prepared.hostConfig,
      url: prepared.chatUrl,
      method: "POST",
      body: prepared.inferenceBody,
    });
    const normalized = normalizeServiceChatResult({
      runnerKind: resolved.deployment.runnerKind,
      response: rawResult,
      latencyMs: Date.now() - startedAt,
    });

    const persisted = await persistLiveSessionSuccess({
      db: input.db,
      session: resolved.session,
      deployment: resolved.deployment,
      inferHost: resolved.inferHost,
      prepared,
      result: normalized.result,
      outputText: normalized.outputText,
      streaming: false,
    });

    return jsonResult({
      session: persisted.updatedSession,
      userTurn: persisted.userTurn,
      assistantTurn: persisted.assistantTurn,
      inferenceTrace: persisted.inferenceTrace,
      result: normalized.result,
      deployment: persisted.updatedDeployment,
      artifacts: prepared.artifacts,
      toolLoop,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const failed = await persistLiveSessionError({
      db: input.db,
      session: resolved.session,
      deployment: resolved.deployment,
      prepared,
      message,
      streaming: false,
    });

    return jsonResult(
      {
        error: message,
        session: failed.updatedSession,
        deployment: failed.updatedDeployment,
        probe: failed.probe,
        artifacts: prepared.artifacts,
      },
      502
    );
  }
}

export async function startLiveSessionStreamService(input: {
  db: AgentDbClient;
  sessionId: string;
  body?: Record<string, unknown> | null;
  signal?: AbortSignal | null;
}) {
  const session = await loadLiveSessionGraph(input.db, input.sessionId);
  const resolved = resolveLiveSessionContext(session);
  if (!resolved.ok) {
    return resolved.error;
  }
  const { session: liveSession, deployment, inferHost } = resolved;

  const body = input.body ?? {};
  const content = readTrimmedString(body.content);
  if (content.length === 0) {
    return jsonResult({ error: "content is required" }, 400);
  }

  const { prepared, toolLoop } = buildPreparedLiveSessionInput({
    session: liveSession,
    deployment,
    inferHost,
    content,
    body,
    source: "live_stream",
  });
  const remoteCommand = buildRemoteHttpCommand({
    url: prepared.streamUrl,
    method: "POST",
    body: prepared.streamInferenceBody,
    noBuffer: true,
  });

  async function* eventStream() {
    let stderrBuffer = "";
    let streamedAssistantText = "";
    let promptTokens: number | null = null;
    let completionTokens: number | null = null;
    const streamStartedAt = Date.now();

    const finalizeSuccess = async (payloadValue: Record<string, unknown>) => {
      const outputText = readTrimmedString(payloadValue.output_text) || streamedAssistantText;
      const persisted = await persistLiveSessionSuccess({
        db: input.db,
        session: liveSession,
        deployment,
        inferHost,
        prepared,
        result: payloadValue,
        outputText,
        streaming: true,
      });

      return {
        type: "persisted",
        userTurn: persisted.userTurn,
        assistantTurn: persisted.assistantTurn,
        inferenceTrace: persisted.inferenceTrace,
        session: persisted.updatedSession,
        deployment: persisted.updatedDeployment,
        artifacts: prepared.artifacts,
        toolLoop,
      } as Record<string, unknown>;
    };

    const finalizeError = async (message: string) => {
      const failed = await persistLiveSessionError({
        db: input.db,
        session: liveSession,
        deployment,
        prepared,
        message,
        streaming: true,
        stderrBuffer,
      });

      return {
        type: "error",
        error: message,
        session: failed.updatedSession,
        deployment: failed.updatedDeployment,
        artifacts: prepared.artifacts,
        probe: failed.probe,
      } as Record<string, unknown>;
    };

    try {
      await waitForLiveServiceReady({
        host: prepared.hostConfig,
        sessionName: prepared.artifacts.sessionName,
        statusPath: prepared.artifacts.statusPath,
        logPath: prepared.artifacts.logPath,
        baseUrl: prepared.artifacts.baseUrl,
      });
    } catch (error) {
      yield await finalizeError(error instanceof Error ? error.message : String(error));
      return;
    }

    try {
      let exitCode: number | null = null;
      for await (const event of streamRemoteSseOverSsh({
        host: prepared.hostConfig,
        remoteCommand,
        signal: input.signal,
      })) {
        if (event.kind === "stderr") {
          stderrBuffer += event.chunk;
          continue;
        }
        if (event.kind === "payload") {
          if (isVllmOpenAiRunner(deployment.runnerKind)) {
            const parsed = parseVllmStreamPayload(event.payload);
            if (parsed.promptTokens !== null) {
              promptTokens = parsed.promptTokens;
            }
            if (parsed.completionTokens !== null) {
              completionTokens = parsed.completionTokens;
            }
            if (parsed.errorText) {
              stderrBuffer = [stderrBuffer, parsed.errorText].filter(Boolean).join("\n");
              yield { type: "error", error: parsed.errorText };
              continue;
            }
            if (parsed.deltaText.length > 0) {
              streamedAssistantText += parsed.deltaText;
              yield { type: "chunk", delta: parsed.deltaText };
              continue;
            }
            if (parsed.done) {
              const donePayload = buildVllmDonePayload({
                outputText: streamedAssistantText,
                latencyMs: Date.now() - streamStartedAt,
                promptTokens,
                completionTokens,
              });
              yield donePayload;
              yield await finalizeSuccess(donePayload);
              return;
            }
            continue;
          }

          const type = readTrimmedString(event.payload.type);
          if (type === "chunk") {
            streamedAssistantText += readTrimmedString(event.payload.delta);
          } else if (type === "error") {
            stderrBuffer = [stderrBuffer, readTrimmedString(event.payload.error)].filter(Boolean).join("\n");
          } else if (type === "done") {
            streamedAssistantText =
              readTrimmedString(event.payload.output_text) ||
              readTrimmedString(event.payload.raw_output_text) ||
              streamedAssistantText;
          }

          yield event.payload;

          if (type === "done") {
            yield await finalizeSuccess(event.payload);
            return;
          }
          continue;
        }
        exitCode = event.code;
      }

      const baseMessage = stderrBuffer.trim() || `remote stream exited with code ${exitCode ?? "unknown"}`;
      if (baseMessage.includes("404")) {
        try {
          yield { type: "meta", mode: "chat_fallback", reason: "stream_endpoint_unavailable" };
          const startedAt = Date.now();
          const chatPayload = await remoteHttpJson({
            host: prepared.hostConfig,
            url: prepared.chatUrl,
            method: "POST",
            body: prepared.inferenceBody,
          });
          const normalized = normalizeServiceChatResult({
            runnerKind: deployment.runnerKind,
            response: chatPayload,
            latencyMs: Date.now() - startedAt,
          });
          const finalPayload = normalized.result;
          streamedAssistantText = normalized.outputText;
          const donePayload = {
            type: "done",
            ...finalPayload,
            output_text: streamedAssistantText,
          } as Record<string, unknown>;
          yield donePayload;
          yield await finalizeSuccess(donePayload);
          return;
        } catch (error) {
          yield await finalizeError(error instanceof Error ? error.message : String(error));
          return;
        }
      }

      yield await finalizeError(baseMessage);
    } catch (error) {
      yield await finalizeError(error instanceof Error ? error.message : String(error));
    }
  }

  return {
    status: 200 as const,
    stream: eventStream(),
  };
}
