import {
  buildLiveServiceArtifacts,
  defaultServicePortForSlug,
  launchLiveService,
  nextLiveServiceStatus,
  probeLiveService,
  stopLiveService,
  summarizeLiveServiceError,
} from "@ququ/agent/remoteJobs";
import { defaultServicePathsForRunner } from "@ququ/agent/serviceProtocol";
import {
  asBoolean,
  asNumber,
  asString,
  buildHostConfig,
  type AgentDbClient,
  jsonResult,
  jsonStringOrNull,
} from "./shared";

function resolvePort(baseUrl: string | null, slug: string) {
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

async function loadDeployment(db: AgentDbClient, deploymentId: string) {
  return db.modelDeployment.findUnique({
    where: { id: deploymentId },
    include: { inferHost: true },
  });
}

export async function startModelDeploymentService(input: {
  db: AgentDbClient;
  deploymentId: string;
  body?: Record<string, unknown> | null;
}) {
  const deployment = await loadDeployment(input.db, input.deploymentId);
  if (!deployment?.inferHost) {
    return jsonResult({ error: "Deployment not found" }, 404);
  }
  if (deployment.serviceMode === "offline_only") {
    return jsonResult({ error: "Deployment is offline_only" }, 400);
  }

  const body = input.body ?? {};
  const port = asNumber(body.port, resolvePort(deployment.serviceBaseUrl, deployment.slug));
  const device = asString(body.device) || deployment.defaultDevice;
  const host = asString(body.host) || "127.0.0.1";
  const maxNewTokensDefault = asNumber(body.maxNewTokensDefault, 256);
  const forceRestart = asBoolean(body.forceRestart);
  const systemPromptFile = asString(body.systemPromptFile) || deployment.systemPromptFile || undefined;
  const promptVersion = deployment.systemPromptFile
    ? deployment.systemPromptFile.split("/").pop()?.replace(/\.[^.]+$/, "") || "default"
    : "default";
  const artifacts = buildLiveServiceArtifacts(deployment.inferHost.workspacePath, deployment.slug, port);
  const servicePaths = defaultServicePathsForRunner(deployment.runnerKind);
  const hostConfig = buildHostConfig(deployment.inferHost);

  let probe = null;
  try {
    probe = await probeLiveService({
      host: hostConfig!,
      sessionName: artifacts.sessionName,
      statusPath: artifacts.statusPath,
      logPath: artifacts.logPath,
      baseUrl: artifacts.baseUrl,
    });

    const probedStatus = nextLiveServiceStatus(probe);
    const probedDeployment = await input.db.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: probedStatus,
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: probe.exitCode,
        serviceLastError: summarizeLiveServiceError(probe),
        serviceLastHealthJson: jsonStringOrNull(probe.healthJson),
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });

    if (forceRestart === false && (probedStatus === "starting" || probedStatus === "running_service")) {
      return jsonResult({
        deployment: probedDeployment,
        artifacts,
        probe,
        skipped: true,
        reason: probedStatus === "running_service" ? "already_running" : "already_starting",
      });
    }
  } catch {
    probe = null;
  }

  if (forceRestart === false) {
    const claim = await input.db.modelDeployment.updateMany({
      where: {
        id: deployment.id,
        serviceStatus: { notIn: ["starting", "running_service"] },
      },
      data: {
        serviceStatus: "starting",
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: null,
        serviceLastError: null,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
    });

    if (claim.count === 0) {
      const current = await loadDeployment(input.db, deployment.id);
      return jsonResult({
        deployment: current,
        artifacts,
        probe,
        skipped: true,
        reason: "already_starting",
      });
    }
  }

  try {
    const launch = await launchLiveService({
      host: hostConfig!,
      deployment: {
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerScriptPath: deployment.runnerScriptPath,
        runnerKind: deployment.runnerKind,
        defaultDevice: deployment.defaultDevice,
        slug: deployment.slug,
        deploymentId: deployment.id,
        promptVersion,
        generationConfigVersion: "v1",
        contextBuilderVersion: "v1",
      },
      config: {
        port,
        host,
        device,
        maxNewTokensDefault,
        systemPromptFile,
      },
    });

    const updated = await input.db.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "starting",
        serviceBaseUrl: launch.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: launch.sessionName,
        serviceLogPath: launch.logPath,
        serviceStatusPath: launch.statusPath,
        serviceLastExitCode: null,
        serviceLastError: null,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });

    return jsonResult({ deployment: updated, launch, artifacts: launch });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const updated = await input.db.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "failed_launch",
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: null,
        serviceLastError: message,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });
    return jsonResult({ error: message, deployment: updated, artifacts }, 500);
  }
}

export async function checkModelDeploymentHealthService(input: {
  db: AgentDbClient;
  deploymentId: string;
}) {
  const deployment = await loadDeployment(input.db, input.deploymentId);
  if (!deployment?.inferHost) {
    return jsonResult({ error: "Deployment not found" }, 404);
  }

  const port = resolvePort(deployment.serviceBaseUrl, deployment.slug);
  const artifacts = buildLiveServiceArtifacts(deployment.inferHost.workspacePath, deployment.slug, port);
  const servicePaths = defaultServicePathsForRunner(deployment.runnerKind);

  try {
    const probe = await probeLiveService({
      host: buildHostConfig(deployment.inferHost)!,
      sessionName: artifacts.sessionName,
      statusPath: artifacts.statusPath,
      logPath: artifacts.logPath,
      baseUrl: artifacts.baseUrl,
    });

    const updated = await input.db.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: nextLiveServiceStatus(probe),
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: probe.exitCode,
        serviceLastError: summarizeLiveServiceError(probe),
        serviceLastHealthJson: jsonStringOrNull(probe.healthJson),
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });

    return jsonResult({ deployment: updated, probe, artifacts });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const updated = await input.db.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "error",
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
        serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastError: message,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });
    return jsonResult({ error: message, deployment: updated, artifacts }, 500);
  }
}

export async function stopModelDeploymentService(input: {
  db: AgentDbClient;
  deploymentId: string;
}) {
  const deployment = await loadDeployment(input.db, input.deploymentId);
  if (!deployment?.inferHost) {
    return jsonResult({ error: "Deployment not found" }, 404);
  }

  const port = resolvePort(deployment.serviceBaseUrl, deployment.slug);
  const artifacts = buildLiveServiceArtifacts(deployment.inferHost.workspacePath, deployment.slug, port);
  const servicePaths = defaultServicePathsForRunner(deployment.runnerKind);

  await stopLiveService({
    host: buildHostConfig(deployment.inferHost)!,
    sessionName: artifacts.sessionName,
  });

  const updated = await input.db.modelDeployment.update({
    where: { id: deployment.id },
    data: {
      serviceStatus: "stopped",
      serviceBaseUrl: artifacts.baseUrl,
      serviceChatPath: deployment.serviceChatPath || servicePaths.chatPath,
      serviceStreamPath: deployment.serviceStreamPath || servicePaths.streamPath,
      serviceSessionName: artifacts.sessionName,
      serviceLogPath: artifacts.logPath,
      serviceStatusPath: artifacts.statusPath,
      serviceLastExitCode: null,
      serviceLastError: null,
      serviceLastHealthJson: null,
      serviceLastCheckedAt: new Date(),
    },
    include: { inferHost: true },
  });

  return jsonResult({
    deployment: updated,
    stopped: true,
    sessionName: artifacts.sessionName,
    artifacts,
  });
}
