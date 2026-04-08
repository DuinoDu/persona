import {
  loadBatchTraceFromRun,
  loadGenerationRecordsFromRun,
} from "@ququ/agent/evalArtifacts";
import {
  launchOfflineEvalJob,
  probeOfflineEvalJob,
} from "@ququ/agent/remoteJobs";
import {
  asBoolean,
  asIntegerOrNull,
  asNumber,
  asOptionalString,
  asRecord,
  asString,
  buildHostConfig,
  type AgentDbClient,
  jsonResult,
  jsonString,
} from "./shared";

export async function listEvalRunsService(input: { db: AgentDbClient }) {
  const items = await input.db.evalRun.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });
  return jsonResult({ items });
}

export async function createEvalRunService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const inferHostId = asString(body.inferHostId);
  const modelDeploymentId = asString(body.modelDeploymentId);
  const evalSuiteId = asString(body.evalSuiteId);
  const autoLaunch = asBoolean(body.autoLaunch);

  if (!inferHostId || !modelDeploymentId || !evalSuiteId) {
    return jsonResult({ error: "Missing required fields" }, 400);
  }

  const [host, deployment, suite] = await Promise.all([
    input.db.inferHost.findUnique({ where: { id: inferHostId } }),
    input.db.modelDeployment.findUnique({ where: { id: modelDeploymentId } }),
    input.db.evalSuite.findUnique({ where: { id: evalSuiteId } }),
  ]);

  if (!host || !deployment || !suite) {
    return jsonResult({ error: "Host / Deployment / Suite not found" }, 404);
  }

  const promptVersion = deployment.systemPromptFile
    ? deployment.systemPromptFile.split("/").pop()?.replace(/\.[^.]+$/, "") || "default"
    : "default";
  const config = {
    maxNewTokens: asNumber(body.maxNewTokens, 256),
    device: asString(body.device) || deployment.defaultDevice,
    doSample: asBoolean(body.doSample),
    temperature: asNumber(body.temperature, 0.7),
    topP: asNumber(body.topP, 0.95),
    systemPromptFile: asOptionalString(body.systemPromptFile),
    deploymentId: deployment.id,
    slug: deployment.slug,
    promptVersion,
    generationConfigVersion: "v1",
    contextBuilderVersion: "v1",
    autoLaunch,
  };

  const title = asString(body.title) || `${suite.title} @ ${deployment.name}`;
  let run = await input.db.evalRun.create({
    data: {
      inferHostId,
      modelDeploymentId,
      evalSuiteId,
      title,
      mode: "offline",
      kind: "suite_batch",
      status: autoLaunch ? "queued" : "draft",
      configJson: JSON.stringify(config),
    },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!autoLaunch) {
    return jsonResult(run);
  }

  try {
    const launch = await launchOfflineEvalJob({
      host: buildHostConfig(host)!,
      deployment: {
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerScriptPath: deployment.runnerScriptPath,
        defaultDevice: deployment.defaultDevice,
        deploymentId: deployment.id,
        slug: deployment.slug,
        promptVersion,
        generationConfigVersion: "v1",
        contextBuilderVersion: "v1",
      },
      suite: {
        sourcePath: suite.sourcePath,
        slug: suite.slug,
      },
      runId: run.id,
      config,
    });

    run = await input.db.evalRun.update({
      where: { id: run.id },
      data: {
        status: "running",
        outputDir: launch.outputDir,
        logPath: launch.logPath,
        statusPath: launch.statusPath,
        summaryPath: launch.summaryPath,
        tmuxSession: launch.sessionName,
        remoteCommand: launch.remoteCommand,
        startedAt: new Date(),
      },
      include: {
        inferHost: true,
        modelDeployment: true,
        evalSuite: true,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    run = await input.db.evalRun.update({
      where: { id: run.id },
      data: {
        status: "failed_launch",
        error: message,
      },
      include: {
        inferHost: true,
        modelDeployment: true,
        evalSuite: true,
      },
    });
  }

  return jsonResult(run);
}

export async function getEvalRunService(input: {
  db: AgentDbClient;
  runId: string;
  refresh?: boolean;
}) {
  let run = await input.db.evalRun.findUnique({
    where: { id: input.runId },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    return jsonResult({ error: "Run not found" }, 404);
  }

  if (
    input.refresh &&
    run.mode === "offline" &&
    run.inferHost &&
    run.tmuxSession &&
    run.statusPath &&
    run.summaryPath &&
    ["queued", "running"].includes(run.status)
  ) {
    try {
      const probe = await probeOfflineEvalJob({
        host: buildHostConfig(run.inferHost)!,
        tmuxSession: run.tmuxSession,
        statusPath: run.statusPath,
        summaryPath: run.summaryPath,
      });

      let nextStatus = run.status;
      let finishedAt = run.finishedAt;
      if (probe.exitCode !== null) {
        nextStatus = probe.exitCode === 0 ? "succeeded" : "failed";
        finishedAt = finishedAt || new Date();
      } else if (probe.sessionState === "alive") {
        nextStatus = "running";
      }

      run = await input.db.evalRun.update({
        where: { id: run.id },
        data: {
          status: nextStatus,
          finishedAt,
          resultJson: probe.summaryJson || run.resultJson,
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          evalSuite: true,
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      run = await input.db.evalRun.update({
        where: { id: run.id },
        data: {
          error: message,
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          evalSuite: true,
        },
      });
    }
  }

  return jsonResult(run);
}

export async function ingestEvalRunTracesService(input: {
  db: AgentDbClient;
  runId: string;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const force = asBoolean(body.force);

  const run = await input.db.evalRun.findUnique({
    where: { id: input.runId },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    return jsonResult({ error: "Run not found" }, 404);
  }

  const runRef = {
    outputDir: run.outputDir,
    summaryPath: run.summaryPath,
    inferHost: buildHostConfig(run.inferHost),
  };

  const records = await loadGenerationRecordsFromRun(runRef);
  if (records.length === 0) {
    return jsonResult({ error: "No generation records found for run" }, 400);
  }

  const caseIds = records.map((record) => record.id);
  const existing = await input.db.inferenceTrace.findMany({
    where: {
      evalRunId: run.id,
      caseId: { in: caseIds },
      sourceType: "offline_case",
    },
    select: { id: true, caseId: true },
  });
  const existingByCaseId = new Map<string, { id: string; caseId: string | null }>(
    existing.map((item: { id: string; caseId: string | null }) => [item.caseId || "", item])
  );

  let imported = 0;
  let skipped = 0;
  let updated = 0;
  let missingTraceArtifacts = 0;

  for (const record of records) {
    const existingRow = existingByCaseId.get(record.id);
    if (existingRow && !force) {
      skipped += 1;
      continue;
    }

    const trace = await loadBatchTraceFromRun(runRef, record.id);
    if (!trace) {
      missingTraceArtifacts += 1;
    }

    const runtimeSignature = trace?.runtime_signature || record.runtimeSignature || null;
    const request = asRecord(trace?.request);
    const response = asRecord(trace?.response);
    const metrics = asRecord(trace?.metrics);
    const artifacts = asRecord(trace?.artifacts);
    const traceMeta = request ? asRecord(request.trace_meta) : null;
    const messages = Array.isArray(request?.messages) ? request?.messages : record.messages;
    const generation = asRecord(request?.generation) || record.generation || null;
    const outputText = asString(response?.clean_output_text) || record.cleanOutputText || record.rawOutputText;
    const rawOutput = response || {
      raw_output_text: record.rawOutputText,
      clean_output_text: record.cleanOutputText,
      generated_tokens: record.generatedTokens,
      prompt_tokens: record.promptTokens,
      latency_ms: record.latencyMs,
      contains_control_tokens: record.containsControlTokens,
      blank_output: record.blankOutput,
      short_output: record.shortOutput,
    };

    const data = {
      sourceType: "offline_case",
      sourceId: `${run.id}:${record.id}`,
      inferHostId: run.inferHostId,
      modelDeploymentId: run.modelDeploymentId,
      evalRunId: run.id,
      liveSessionId: null,
      liveTurnId: null,
      promptVersionId: run.modelDeployment?.promptVersionId ?? null,
      generationConfigProfileId: run.modelDeployment?.generationConfigProfileId ?? null,
      contextBuilderProfileId: run.modelDeployment?.contextBuilderProfileId ?? null,
      caseId: record.id,
      status: run.status === "failed" ? "error" : "succeeded",
      runtimeSignatureJson: jsonString(runtimeSignature),
      finalMessagesJson: jsonString(messages),
      generationConfigJson: jsonString(generation),
      traceMetaJson: jsonString(traceMeta),
      summarySnapshotJson: null,
      trimReportJson: null,
      estimatedPromptTokens: asIntegerOrNull(metrics?.prompt_tokens) ?? record.promptTokens,
      generatedTokens: asIntegerOrNull(metrics?.generated_tokens) ?? record.generatedTokens,
      readyWaitMs: null,
      firstTokenLatencyMs: null,
      totalLatencyMs: asIntegerOrNull(metrics?.latency_ms) ?? record.latencyMs,
      outputText,
      rawOutputJson: jsonString(rawOutput),
      remoteLogPath: run.logPath,
      remoteArtifactPath: asString(artifacts?.trace_path) || record.tracePath || null,
      error: null,
    };

    if (existingRow) {
      await input.db.inferenceTrace.update({
        where: { id: existingRow.id },
        data,
      });
      updated += 1;
    } else {
      await input.db.inferenceTrace.create({ data });
      imported += 1;
    }
  }

  return jsonResult({
    runId: run.id,
    totalCases: records.length,
    imported,
    updated,
    skipped,
    missingTraceArtifacts,
    force,
  });
}
