export interface DeploymentItem {
  id: string;
  name: string;
  slug: string;
  inferHostName: string;
  inferHostId: string;
  serviceMode: string;
  serviceStatus: string;
  serviceBaseUrl: string | null;
  serviceChatPath: string | null;
  serviceStreamPath: string | null;
  serviceSessionName: string | null;
  serviceLogPath: string | null;
  serviceStatusPath: string | null;
  serviceLastExitCode: number | null;
  serviceLastError: string | null;
  serviceLastHealthJson: string | null;
  serviceLastCheckedAt: string | null;
  notes: string | null;
}

export interface LiveTurnItem {
  id: string;
  role: string;
  content: string;
  latencyMs: number | null;
  tokenCount: number | null;
  createdAt: string;
}

export interface LiveSessionItem {
  id: string;
  title: string;
  status: string;
  scenario: string | null;
  notes: string | null;
  inferHostId: string | null;
  modelDeploymentId: string | null;
  modelDeploymentName: string | null;
  inferHostName: string | null;
  createdAt: string;
  updatedAt: string;
  turns: LiveTurnItem[];
}

export interface ServiceArtifacts {
  sessionName: string;
  logPath: string;
  statusPath: string;
  baseUrl: string;
  healthUrl: string;
  chatUrl: string;
  port: number | null;
  listenHost: string | null;
}

export interface ServiceProbe {
  sessionState: string;
  exitCode: number | null;
  healthJson: unknown;
  logTail: string | null;
}

export interface ServiceDebugState {
  artifacts: ServiceArtifacts | null;
  probe: ServiceProbe | null;
  updatedAt: string;
}

export interface LiveInferConsoleProps {
  deployments: DeploymentItem[];
  initialSessions: LiveSessionItem[];
}

export function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

export function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

export function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function asNullableNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function normalizeDeployment(value: unknown): DeploymentItem {
  const record = asRecord(value) || {};
  const inferHost = asRecord(record.inferHost);
  return {
    id: asString(record.id),
    name: asString(record.name),
    slug: asString(record.slug),
    inferHostName: asString(record.inferHostName) || asString(inferHost?.name) || "-",
    inferHostId: asString(record.inferHostId) || asString(inferHost?.id),
    serviceMode: asString(record.serviceMode) || "offline_only",
    serviceStatus: asString(record.serviceStatus) || "stopped",
    serviceBaseUrl: asNullableString(record.serviceBaseUrl),
    serviceChatPath: asNullableString(record.serviceChatPath),
    serviceStreamPath: asNullableString(record.serviceStreamPath),
    serviceSessionName: asNullableString(record.serviceSessionName),
    serviceLogPath: asNullableString(record.serviceLogPath),
    serviceStatusPath: asNullableString(record.serviceStatusPath),
    serviceLastExitCode: asNullableNumber(record.serviceLastExitCode),
    serviceLastError: asNullableString(record.serviceLastError),
    serviceLastHealthJson: asNullableString(record.serviceLastHealthJson),
    serviceLastCheckedAt: asNullableString(record.serviceLastCheckedAt),
    notes: asNullableString(record.notes),
  };
}

export function normalizeTurn(value: unknown): LiveTurnItem {
  const record = asRecord(value) || {};
  return {
    id: asString(record.id),
    role: asString(record.role) || "user",
    content: asString(record.content),
    latencyMs: asNullableNumber(record.latencyMs),
    tokenCount: asNullableNumber(record.tokenCount),
    createdAt: asString(record.createdAt),
  };
}

export function normalizeSession(value: unknown): LiveSessionItem {
  const record = asRecord(value) || {};
  const inferHost = asRecord(record.inferHost);
  const deployment = asRecord(record.modelDeployment);
  const turnsRaw = Array.isArray(record.turns) ? record.turns : [];
  return {
    id: asString(record.id),
    title: asString(record.title),
    status: asString(record.status) || "draft",
    scenario: asNullableString(record.scenario),
    notes: asNullableString(record.notes),
    inferHostId: asNullableString(record.inferHostId) || asNullableString(inferHost?.id),
    modelDeploymentId: asNullableString(record.modelDeploymentId) || asNullableString(deployment?.id),
    modelDeploymentName: asNullableString(record.modelDeploymentName) || asNullableString(deployment?.name),
    inferHostName: asNullableString(record.inferHostName) || asNullableString(inferHost?.name),
    createdAt: asString(record.createdAt),
    updatedAt: asString(record.updatedAt),
    turns: turnsRaw.map(normalizeTurn),
  };
}

export function normalizeServiceArtifacts(value: unknown): ServiceArtifacts | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const sessionName = asString(record.sessionName);
  const logPath = asString(record.logPath);
  const statusPath = asString(record.statusPath);
  const baseUrl = asString(record.baseUrl);
  if (!sessionName && !logPath && !statusPath && !baseUrl) {
    return null;
  }
  return {
    sessionName,
    logPath,
    statusPath,
    baseUrl,
    healthUrl: asString(record.healthUrl),
    chatUrl: asString(record.chatUrl),
    port: asNullableNumber(record.port),
    listenHost: asNullableString(record.listenHost),
  };
}

export function normalizeServiceProbe(value: unknown): ServiceProbe | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    sessionState: asString(record.sessionState) || "unknown",
    exitCode: asNullableNumber(record.exitCode),
    healthJson: record.healthJson ?? null,
    logTail: asNullableString(record.logTail),
  };
}
