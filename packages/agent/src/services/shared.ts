import type { InferHostJobConfig } from "@ququ/agent/remoteJobs";

export interface AgentDbClient {
  [key: string]: any;
  $transaction: any;
}

export interface JsonServiceResult<T = unknown> {
  status: number;
  body: T;
}

export function jsonResult<T>(body: T, status = 200): JsonServiceResult<T> {
  return { status, body };
}

export function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

export function asOptionalString(value: unknown) {
  const text = asString(value);
  return text.length > 0 ? text : null;
}

export function asBoolean(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value === "true" || value === "1" || value === "on";
  return false;
}

export function asNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function asPort(value: unknown) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 22;
}

export function asIntegerOrNull(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? Math.floor(value) : null;
}

export function asDate(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => asString(item)).filter(Boolean) : [];
}

export function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

export function jsonString(value: unknown) {
  return JSON.stringify(value ?? null);
}

export function jsonStringOrNull(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }
  return JSON.stringify(value);
}

export function parseJsonMaybe(value: string | null | undefined) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function uniqueStrings(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

export function buildHostConfig(host: {
  sshHost: string;
  sshPort: number;
  sshUser: string;
  workspacePath: string;
} | null | undefined): InferHostJobConfig | null {
  if (!host) {
    return null;
  }
  return {
    sshHost: host.sshHost,
    sshPort: host.sshPort,
    sshUser: host.sshUser,
    workspacePath: host.workspacePath,
  };
}
