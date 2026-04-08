import { type AgentDbClient, asOptionalString, asPort, asString, jsonResult } from "./shared";

export async function listInferHostsService(input: { db: AgentDbClient }) {
  const items = await input.db.inferHost.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      _count: {
        select: {
          deployments: true,
          evalRuns: true,
          liveSessions: true,
        },
      },
    },
  });
  return jsonResult({ items });
}

export async function createInferHostService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const name = asString(body.name);
  const sshHost = asString(body.sshHost);
  const sshUser = asString(body.sshUser);
  const workspacePath = asString(body.workspacePath);

  if (!name || !sshHost || !sshUser || !workspacePath) {
    return jsonResult({ error: "Missing required fields" }, 400);
  }

  const host = await input.db.inferHost.create({
    data: {
      name,
      sshHost,
      sshPort: asPort(body.sshPort),
      sshUser,
      workspacePath,
      gpuPolicy: asString(body.gpuPolicy) || "shared_service",
      status: asString(body.status) || "active",
      notes: asOptionalString(body.notes),
    },
  });

  return jsonResult(host);
}

export async function listModelDeploymentsService(input: { db: AgentDbClient }) {
  const items = await input.db.modelDeployment.findMany({
    orderBy: { createdAt: "desc" },
    include: { inferHost: true },
  });
  return jsonResult({ items });
}

export async function createModelDeploymentService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const inferHostId = asString(body.inferHostId);
  const name = asString(body.name);
  const slug = asString(body.slug);
  const baseModelPath = asString(body.baseModelPath);

  if (!inferHostId || !name || !slug || !baseModelPath) {
    return jsonResult({ error: "Missing required fields" }, 400);
  }

  const deployment = await input.db.modelDeployment.create({
    data: {
      inferHostId,
      name,
      slug,
      baseModelPath,
      adapterPath: asOptionalString(body.adapterPath),
      systemPromptFile: asOptionalString(body.systemPromptFile),
      runnerKind: asString(body.runnerKind) || "batch_chat_eval",
      runnerScriptPath: asOptionalString(body.runnerScriptPath),
      serviceMode: asString(body.serviceMode) || "offline_only",
      serviceStatus: asString(body.serviceStatus) || "stopped",
      serviceBaseUrl: asOptionalString(body.serviceBaseUrl),
      serviceChatPath: asOptionalString(body.serviceChatPath),
      serviceStreamPath: asOptionalString(body.serviceStreamPath),
      defaultDevice: asString(body.defaultDevice) || "cuda",
      notes: asOptionalString(body.notes),
    },
  });

  return jsonResult(deployment);
}
