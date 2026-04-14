import {
  fetchRemoteEvalAdminSnapshot,
  type RemoteEvalAdminSnapshot,
} from "@ququ/agent/remoteJobs";
import {
  asBoolean,
  asDate,
  asNumber,
  asString,
  type AgentDbClient,
  jsonResult,
} from "./shared";

function buildFallbackSnapshot(input: {
  sshHost: string;
  sshPort: number;
  sshUser: string;
  workspacePath: string;
  importRuns: boolean;
}): RemoteEvalAdminSnapshot {
  const inferHostId = "infer_host_h20_local";
  const baseDeploymentId = "deploy_qwen35_9b_base";
  const finalDeploymentId = "deploy_qwen35_9b_final";
  const suiteId = "suite_persona_baseline_smoke_v1";
  const baseModelPath = `${input.workspacePath}/.cache/modelscope/Qwen/Qwen3.5-9B`;
  const systemPromptFile = `${input.workspacePath}/artifacts/llamafactory_data/system_anchor_v1.txt`;
  const runnerScriptPath = `${input.workspacePath}/packages/agent/scripts/evals/run_batch_chat_eval_py312.sh`;
  const finalAdapterPath =
    `${input.workspacePath}/outputs/exp_sft_turn_only_qwen3_5_9b_h20_v1/` +
    `baseline_20260329_070329/final_adapter`;

  const evalRuns = input.importRuns
    ? [
        {
          id: "run_eval_smoke_gpu_20260407_133940_b",
          inferHostId,
          modelDeploymentId: baseDeploymentId,
          evalSuiteId: suiteId,
          title: "Persona Baseline Smoke GPU @ Base",
          mode: "offline",
          kind: "suite_batch",
          status: "succeeded",
          outputDir: `${input.workspacePath}/artifacts/evals/runs/run_eval_smoke_gpu_20260407_133940_b`,
          logPath: `${input.workspacePath}/runtime_logs/evals/run_eval_smoke_gpu_20260407_133940_b.log`,
          statusPath: `${input.workspacePath}/runtime_logs/evals/run_eval_smoke_gpu_20260407_133940_b.status`,
          summaryPath: `${input.workspacePath}/artifacts/evals/runs/run_eval_smoke_gpu_20260407_133940_b/summary.json`,
          tmuxSession: "persona_eval_7_133940_b",
          remoteCommand: null,
          configJson: null,
          resultJson: null,
          error: null,
          startedAt: null,
          finishedAt: null,
          createdAt: null,
          updatedAt: null,
        },
        {
          id: "run_eval_smoke_gpu_20260407_134212_f",
          inferHostId,
          modelDeploymentId: finalDeploymentId,
          evalSuiteId: suiteId,
          title: "Persona Baseline Smoke GPU @ Final",
          mode: "offline",
          kind: "suite_batch",
          status: "succeeded",
          outputDir: `${input.workspacePath}/artifacts/evals/runs/run_eval_smoke_gpu_20260407_134212_f`,
          logPath: `${input.workspacePath}/runtime_logs/evals/run_eval_smoke_gpu_20260407_134212_f.log`,
          statusPath: `${input.workspacePath}/runtime_logs/evals/run_eval_smoke_gpu_20260407_134212_f.status`,
          summaryPath: `${input.workspacePath}/artifacts/evals/runs/run_eval_smoke_gpu_20260407_134212_f/summary.json`,
          tmuxSession: "persona_eval_7_134212_f",
          remoteCommand: null,
          configJson: null,
          resultJson: null,
          error: null,
          startedAt: null,
          finishedAt: null,
          createdAt: null,
          updatedAt: null,
        },
      ]
    : [];

  return {
    inferHosts: [
      {
        id: inferHostId,
        name: "h20-persona",
        sshHost: input.sshHost,
        sshPort: input.sshPort,
        sshUser: input.sshUser,
        workspacePath: input.workspacePath,
        status: "active",
        gpuPolicy: "shared_service",
        notes: "Bootstrapped from local web for H20 persona infer/eval",
      },
    ],
    modelDeployments: [
      {
        id: baseDeploymentId,
        inferHostId,
        name: "Qwen3.5-9B Base",
        slug: "qwen35-9b-base",
        baseModelPath,
        adapterPath: null,
        systemPromptFile,
        runnerKind: "batch_chat_eval",
        runnerScriptPath,
        serviceMode: "offline_only",
        serviceStatus: "stopped",
        serviceBaseUrl: null,
        serviceChatPath: "/chat",
        serviceStreamPath: "/stream",
        serviceSessionName: null,
        serviceLogPath: null,
        serviceStatusPath: null,
        serviceLastExitCode: null,
        serviceLastError: null,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: null,
        defaultDevice: "cuda",
        notes: "Base model deployment for offline eval comparisons",
      },
      {
        id: finalDeploymentId,
        inferHostId,
        name: "Qwen3.5-9B Final Adapter",
        slug: "qwen35-9b-final",
        baseModelPath,
        adapterPath: finalAdapterPath,
        systemPromptFile,
        runnerKind: "vllm_openai",
        runnerScriptPath,
        serviceMode: "dual_mode",
        serviceStatus: "stopped",
        serviceBaseUrl: null,
        serviceChatPath: "/v1/chat/completions",
        serviceStreamPath: "/v1/chat/completions",
        serviceSessionName: null,
        serviceLogPath: null,
        serviceStatusPath: null,
        serviceLastExitCode: null,
        serviceLastError: null,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: null,
        defaultDevice: "cuda",
        notes: "Final SFT adapter deployment for offline eval and live infer",
      },
    ],
    evalSuites: [
      {
        id: suiteId,
        slug: "persona_baseline_smoke_v1",
        title: "Persona Baseline Smoke V1",
        description: "3-case smoke suite for baseline persona comparisons",
        sourcePath: `${input.workspacePath}/artifacts/evals/suites/persona_baseline_smoke_v1.jsonl`,
        caseCount: 3,
        tagsJson: null,
        status: "active",
      },
    ],
    evalRuns,
  };
}

export async function bootstrapInferAdmin(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const sshHost = asString(body.sshHost) || "115.190.130.100";
  const sshPort = asNumber(body.sshPort, 39670);
  const sshUser = asString(body.sshUser) || "root";
  const workspacePath =
    asString(body.workspacePath) || "/vita-vepfs-data/fileset1/usr_data/yueyu/ws/persona";
  const importRuns = asBoolean(body.importRuns);
  const maxRuns = asNumber(body.maxRuns, 20);

  let snapshot: RemoteEvalAdminSnapshot | null = null;
  let bootstrapMode = "remote_snapshot";
  try {
    const remoteSnapshot = await fetchRemoteEvalAdminSnapshot({
      host: {
        sshHost,
        sshPort,
        sshUser,
        workspacePath,
      },
      maxRuns,
    });
    if (
      remoteSnapshot.inferHosts.length > 0 ||
      remoteSnapshot.modelDeployments.length > 0 ||
      remoteSnapshot.evalSuites.length > 0
    ) {
      snapshot = remoteSnapshot;
    }
  } catch {
    snapshot = null;
  }

  if (!snapshot) {
    snapshot = buildFallbackSnapshot({
      sshHost,
      sshPort,
      sshUser,
      workspacePath,
      importRuns,
    });
    bootstrapMode = "fallback_defaults";
  }

  for (const host of snapshot.inferHosts) {
    await input.db.inferHost.upsert({
      where: { id: host.id },
      update: {
        name: host.name,
        sshHost: host.sshHost,
        sshPort: host.sshPort,
        sshUser: host.sshUser,
        workspacePath: host.workspacePath,
        status: host.status,
        gpuPolicy: host.gpuPolicy,
        notes: host.notes,
      },
      create: {
        id: host.id,
        name: host.name,
        sshHost: host.sshHost,
        sshPort: host.sshPort,
        sshUser: host.sshUser,
        workspacePath: host.workspacePath,
        status: host.status,
        gpuPolicy: host.gpuPolicy,
        notes: host.notes,
      },
    });
  }

  for (const deployment of snapshot.modelDeployments) {
    await input.db.modelDeployment.upsert({
      where: { id: deployment.id },
      update: {
        inferHostId: deployment.inferHostId,
        name: deployment.name,
        slug: deployment.slug,
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerKind: deployment.runnerKind,
        runnerScriptPath: deployment.runnerScriptPath,
        serviceMode: deployment.serviceMode,
        serviceStatus: deployment.serviceStatus,
        serviceBaseUrl: deployment.serviceBaseUrl,
        serviceChatPath: deployment.serviceChatPath,
        serviceStreamPath: deployment.serviceStreamPath,
        serviceSessionName: deployment.serviceSessionName,
        serviceLogPath: deployment.serviceLogPath,
        serviceStatusPath: deployment.serviceStatusPath,
        serviceLastExitCode: deployment.serviceLastExitCode,
        serviceLastError: deployment.serviceLastError,
        serviceLastHealthJson: deployment.serviceLastHealthJson,
        serviceLastCheckedAt: asDate(deployment.serviceLastCheckedAt),
        defaultDevice: deployment.defaultDevice,
        notes: deployment.notes,
      },
      create: {
        id: deployment.id,
        inferHostId: deployment.inferHostId,
        name: deployment.name,
        slug: deployment.slug,
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerKind: deployment.runnerKind,
        runnerScriptPath: deployment.runnerScriptPath,
        serviceMode: deployment.serviceMode,
        serviceStatus: deployment.serviceStatus,
        serviceBaseUrl: deployment.serviceBaseUrl,
        serviceChatPath: deployment.serviceChatPath,
        serviceStreamPath: deployment.serviceStreamPath,
        serviceSessionName: deployment.serviceSessionName,
        serviceLogPath: deployment.serviceLogPath,
        serviceStatusPath: deployment.serviceStatusPath,
        serviceLastExitCode: deployment.serviceLastExitCode,
        serviceLastError: deployment.serviceLastError,
        serviceLastHealthJson: deployment.serviceLastHealthJson,
        serviceLastCheckedAt: asDate(deployment.serviceLastCheckedAt),
        defaultDevice: deployment.defaultDevice,
        notes: deployment.notes,
      },
    });
  }

  for (const suite of snapshot.evalSuites) {
    await input.db.evalSuite.upsert({
      where: { id: suite.id },
      update: {
        slug: suite.slug,
        title: suite.title,
        description: suite.description,
        sourcePath: suite.sourcePath,
        caseCount: suite.caseCount,
        tagsJson: suite.tagsJson,
        status: suite.status,
      },
      create: {
        id: suite.id,
        slug: suite.slug,
        title: suite.title,
        description: suite.description,
        sourcePath: suite.sourcePath,
        caseCount: suite.caseCount,
        tagsJson: suite.tagsJson,
        status: suite.status,
      },
    });
  }

  let importedRuns = 0;
  if (importRuns) {
    for (const run of snapshot.evalRuns) {
      await input.db.evalRun.upsert({
        where: { id: run.id },
        update: {
          inferHostId: run.inferHostId,
          modelDeploymentId: run.modelDeploymentId,
          evalSuiteId: run.evalSuiteId,
          title: run.title,
          mode: run.mode,
          kind: run.kind,
          status: run.status,
          outputDir: run.outputDir,
          logPath: run.logPath,
          statusPath: run.statusPath,
          summaryPath: run.summaryPath,
          tmuxSession: run.tmuxSession,
          remoteCommand: run.remoteCommand,
          configJson: run.configJson,
          resultJson: run.resultJson,
          error: run.error,
          startedAt: asDate(run.startedAt),
          finishedAt: asDate(run.finishedAt),
        },
        create: {
          id: run.id,
          inferHostId: run.inferHostId,
          modelDeploymentId: run.modelDeploymentId,
          evalSuiteId: run.evalSuiteId,
          title: run.title,
          mode: run.mode,
          kind: run.kind,
          status: run.status,
          outputDir: run.outputDir,
          logPath: run.logPath,
          statusPath: run.statusPath,
          summaryPath: run.summaryPath,
          tmuxSession: run.tmuxSession,
          remoteCommand: run.remoteCommand,
          configJson: run.configJson,
          resultJson: run.resultJson,
          error: run.error,
          startedAt: asDate(run.startedAt),
          finishedAt: asDate(run.finishedAt),
          createdAt: asDate(run.createdAt) || undefined,
        },
      });
      importedRuns += 1;
    }
  }

  return jsonResult({
    ok: true,
    imported: {
      hosts: snapshot.inferHosts.length,
      deployments: snapshot.modelDeployments.length,
      suites: snapshot.evalSuites.length,
      runs: importedRuns,
    },
    mode: bootstrapMode,
    source: {
      sshHost,
      sshPort,
      sshUser,
      workspacePath,
    },
  });
}
