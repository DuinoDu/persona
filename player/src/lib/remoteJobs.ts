import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface InferHostJobConfig {
  sshHost: string;
  sshPort: number;
  sshUser: string;
  workspacePath: string;
}

export interface DeploymentJobConfig {
  baseModelPath: string;
  adapterPath: string | null;
  systemPromptFile: string | null;
  runnerScriptPath: string | null;
  defaultDevice: string;
  slug?: string;
}

export interface SuiteJobConfig {
  sourcePath: string;
  slug: string;
}

export interface OfflineEvalConfig {
  maxNewTokens: number;
  device?: string;
  doSample?: boolean;
  temperature?: number;
  topP?: number;
  systemPromptFile?: string | null;
}

export interface LiveServiceConfig {
  port: number;
  host?: string;
  device?: string;
  maxNewTokensDefault?: number;
  systemPromptFile?: string | null;
}

export interface LiveServiceProbe {
  sessionState: string;
  exitCode: number | null;
  healthJson: unknown;
  logTail: string | null;
}

function shellQuote(value: string) {
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function sanitizeToken(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9_-]+/g, "_");
  return normalized.replace(/^_+|_+$/g, "") || "default";
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

async function runSsh(host: InferHostJobConfig, remoteCommand: string) {
  return execFileAsync("ssh", [
    "-p",
    String(host.sshPort),
    `${host.sshUser}@${host.sshHost}`,
    remoteCommand,
  ]);
}

export function defaultServicePortForSlug(slug: string) {
  let acc = 0;
  for (const ch of slug) {
    acc = (acc + ch.charCodeAt(0)) % 1000;
  }
  return 18080 + acc;
}

export function buildOfflineEvalArtifacts(workspacePath: string, runId: string) {
  return {
    outputDir: `${workspacePath}/artifacts/evals/runs/${runId}`,
    logPath: `${workspacePath}/runtime_logs/evals/${runId}.log`,
    statusPath: `${workspacePath}/runtime_logs/evals/${runId}.status`,
    summaryPath: `${workspacePath}/artifacts/evals/runs/${runId}/summary.json`,
  };
}

export function buildOfflineEvalLaunchSpec(input: {
  host: InferHostJobConfig;
  deployment: DeploymentJobConfig;
  suite: SuiteJobConfig;
  runId: string;
  config: OfflineEvalConfig;
}) {
  const { host, deployment, suite, runId, config } = input;
  const artifacts = buildOfflineEvalArtifacts(host.workspacePath, runId);
  const sessionName = `persona_eval_${runId.slice(-10)}`;
  const runnerScriptPath =
    deployment.runnerScriptPath || `${host.workspacePath}/scripts/evals/run_batch_chat_eval_py312.sh`;

  const args = [
    runnerScriptPath,
    artifacts.logPath,
    artifacts.statusPath,
    artifacts.outputDir,
    "--base-model-path",
    deployment.baseModelPath,
    "--suite-path",
    suite.sourcePath,
    "--device",
    config.device || deployment.defaultDevice || "cuda",
    "--max-new-tokens",
    String(config.maxNewTokens || 256),
  ];

  if (deployment.adapterPath) args.push("--adapter-path", deployment.adapterPath);
  const promptFile = config.systemPromptFile || deployment.systemPromptFile;
  if (promptFile) args.push("--system-prompt-file", promptFile);
  if (config.doSample) {
    args.push(
      "--do-sample",
      "--temperature",
      String(config.temperature ?? 0.7),
      "--top-p",
      String(config.topP ?? 0.95)
    );
  }

  const commandString = args.map(shellQuote).join(" ");
  const remoteCommand = [
    `mkdir -p ${shellQuote(`${host.workspacePath}/runtime_logs/evals`)}`,
    `mkdir -p ${shellQuote(artifacts.outputDir)}`,
    `tmux new-session -d -s ${shellQuote(sessionName)} ${shellQuote(`bash -lc ${shellQuote(commandString)}`)}`,
  ].join(" && ");

  return {
    ...artifacts,
    sessionName,
    remoteCommand,
  };
}

export async function launchOfflineEvalJob(input: {
  host: InferHostJobConfig;
  deployment: DeploymentJobConfig;
  suite: SuiteJobConfig;
  runId: string;
  config: OfflineEvalConfig;
}) {
  const launch = buildOfflineEvalLaunchSpec(input);
  await runSsh(input.host, launch.remoteCommand);
  return launch;
}

export async function probeOfflineEvalJob(input: {
  host: InferHostJobConfig;
  tmuxSession: string;
  statusPath: string;
  summaryPath: string;
}) {
  const probeCommand = [
    `SESSION_STATE=$(tmux has-session -t ${shellQuote(input.tmuxSession)} >/dev/null 2>&1 && echo alive || echo missing)`,
    `STATUS_VALUE=$(if [ -f ${shellQuote(input.statusPath)} ]; then cat ${shellQuote(input.statusPath)}; fi)`,
    'echo __SESSION__=$SESSION_STATE',
    'echo __STATUS__=$STATUS_VALUE',
    `if [ -f ${shellQuote(input.summaryPath)} ]; then echo __SUMMARY_BEGIN__; cat ${shellQuote(input.summaryPath)}; echo __SUMMARY_END__; fi`,
  ].join("; ");

  const { stdout } = await runSsh(input.host, probeCommand);
  const sessionMatch = stdout.match(/__SESSION__=(.*)/);
  const statusMatch = stdout.match(/__STATUS__=(.*)/);
  const summaryMatch = stdout.match(/__SUMMARY_BEGIN__\n([\s\S]*?)\n__SUMMARY_END__/);
  const statusValue = statusMatch?.[1]?.trim() ?? "";

  return {
    sessionState: sessionMatch?.[1]?.trim() || "unknown",
    exitCode: statusValue === "" ? null : Number(statusValue),
    summaryJson: summaryMatch?.[1]?.trim() || null,
  };
}

export function buildLiveServiceArtifacts(workspacePath: string, slug: string, port: number) {
  const token = sanitizeToken(slug).slice(0, 36);
  return {
    sessionName: `persona_live_${token}`,
    logPath: `${workspacePath}/runtime_logs/live/${token}.log`,
    statusPath: `${workspacePath}/runtime_logs/live/${token}.status`,
    baseUrl: `http://127.0.0.1:${port}`,
    healthUrl: `http://127.0.0.1:${port}/health`,
    chatUrl: `http://127.0.0.1:${port}/chat`,
  };
}

export function buildLiveServiceLaunchSpec(input: {
  host: InferHostJobConfig;
  deployment: DeploymentJobConfig;
  config: LiveServiceConfig;
}) {
  const { host, deployment, config } = input;
  const slug = deployment.slug || "live-service";
  const listenHost = config.host || "127.0.0.1";
  const artifacts = buildLiveServiceArtifacts(host.workspacePath, slug, config.port);
  const runnerScriptPath = `${host.workspacePath}/scripts/evals/run_live_chat_service_py312.sh`;
  const args = [
    runnerScriptPath,
    artifacts.logPath,
    artifacts.statusPath,
    listenHost,
    String(config.port),
    "--base-model-path",
    deployment.baseModelPath,
    "--device",
    config.device || deployment.defaultDevice || "cuda",
    "--max-new-tokens-default",
    String(config.maxNewTokensDefault || 256),
  ];
  if (deployment.adapterPath) args.push("--adapter-path", deployment.adapterPath);
  const promptFile = config.systemPromptFile || deployment.systemPromptFile;
  if (promptFile) args.push("--system-prompt-file", promptFile);

  const commandString = args.map(shellQuote).join(" ");
  const remoteCommand = [
    `mkdir -p ${shellQuote(`${host.workspacePath}/runtime_logs/live`)}`,
    `rm -f ${shellQuote(artifacts.statusPath)} ${shellQuote(artifacts.logPath)}`,
    `tmux kill-session -t ${shellQuote(artifacts.sessionName)} >/dev/null 2>&1 || true`,
    `tmux new-session -d -s ${shellQuote(artifacts.sessionName)} ${shellQuote(`bash -lc ${shellQuote(commandString)}`)}`,
  ].join(" && ");

  return {
    ...artifacts,
    remoteCommand,
    listenHost,
    port: config.port,
  };
}

export async function launchLiveService(input: {
  host: InferHostJobConfig;
  deployment: DeploymentJobConfig;
  config: LiveServiceConfig;
}) {
  const launch = buildLiveServiceLaunchSpec(input);
  await runSsh(input.host, launch.remoteCommand);
  return launch;
}

export async function stopLiveService(input: { host: InferHostJobConfig; sessionName: string }) {
  await runSsh(
    input.host,
    `tmux kill-session -t ${shellQuote(input.sessionName)} >/dev/null 2>&1 || true`
  );
  return { stopped: true };
}

export async function remoteHttpJson(input: {
  host: InferHostJobConfig;
  url: string;
  method?: "GET" | "POST";
  body?: unknown;
}) {
  const method = input.method || "GET";
  const bodyText = input.body === undefined ? "" : JSON.stringify(input.body);
  const parts = [
    "curl",
    "-fsS",
    "-X",
    shellQuote(method),
    "-H",
    shellQuote("Content-Type: application/json"),
  ];
  if (method !== "GET") {
    parts.push("--data-binary", shellQuote(bodyText));
  }
  parts.push(shellQuote(input.url));
  const { stdout } = await runSsh(input.host, parts.join(" "));
  return JSON.parse(stdout);
}

export function nextLiveServiceStatus(probe: LiveServiceProbe) {
  const health = asRecord(probe.healthJson);
  if (health) {
    if (health.ready === true) {
      return "running_service";
    }
    if (health.loading === true) {
      return "starting";
    }
    if (typeof health.error === "string" && health.error.length > 0) {
      return "failed";
    }
  }
  if (probe.exitCode !== null) {
    return probe.exitCode === 0 ? "stopped" : "failed";
  }
  if (probe.sessionState === "alive") {
    return "starting";
  }
  return "stopped";
}

export function summarizeLiveServiceError(probe: LiveServiceProbe) {
  const health = asRecord(probe.healthJson);
  const healthError = typeof health?.error === "string" ? health.error.trim() : "";
  if (healthError.length > 0) {
    return healthError;
  }

  const lines = (probe.logTail || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines.slice().reverse()) {
    if (line.includes("Floating-point exception")) {
      return line;
    }
    if (line.startsWith("Fatal Python error:")) {
      return line;
    }
    if (line.includes("CUDA out of memory")) {
      return line;
    }
    if (line.startsWith("RuntimeError:")) {
      return line;
    }
  }

  if (probe.exitCode !== null && probe.exitCode !== 0) {
    return `service exited with code ${probe.exitCode}`;
  }
  if (probe.sessionState === "missing" && health === null) {
    return "service session is not running";
  }
  return null;
}

export async function probeLiveService(input: {
  host: InferHostJobConfig;
  sessionName: string;
  statusPath: string;
  logPath: string;
  baseUrl: string;
}) {
  const probeCommand = [
    `SESSION_STATE=$(tmux has-session -t ${shellQuote(input.sessionName)} >/dev/null 2>&1 && echo alive || echo missing)`,
    `STATUS_VALUE=$(if [ -f ${shellQuote(input.statusPath)} ]; then cat ${shellQuote(input.statusPath)}; fi)`,
    'echo __SESSION__=$SESSION_STATE',
    'echo __STATUS__=$STATUS_VALUE',
    `if [ -f ${shellQuote(input.logPath)} ]; then echo __LOG_BEGIN__; tail -n 60 ${shellQuote(input.logPath)}; echo __LOG_END__; fi`,
  ].join("; ");
  const { stdout } = await runSsh(input.host, probeCommand);
  const sessionMatch = stdout.match(/__SESSION__=(.*)/);
  const statusMatch = stdout.match(/__STATUS__=(.*)/);
  const logMatch = stdout.match(/__LOG_BEGIN__\n([\s\S]*?)\n__LOG_END__/);
  const sessionState = sessionMatch?.[1]?.trim() || "unknown";
  const statusValue = statusMatch?.[1]?.trim() ?? "";

  let healthJson: unknown = null;
  try {
    healthJson = await remoteHttpJson({
      host: input.host,
      url: `${input.baseUrl}/health`,
      method: "GET",
    });
  } catch {
    healthJson = null;
  }

  return {
    sessionState,
    exitCode: statusValue === "" ? null : Number(statusValue),
    healthJson,
    logTail: logMatch?.[1]?.trim() || null,
  } satisfies LiveServiceProbe;
}
