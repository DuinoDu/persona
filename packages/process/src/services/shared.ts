export interface ProcessDbClient {
  [key: string]: any;
  $transaction?: any;
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

export function asOptionalInt(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

export function asOptionalNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asPort(value: unknown) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 22;
}

export function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => asString(item)).filter(Boolean) : [];
}

export function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

export function parseJsonMaybe<T = unknown>(value: string | null | undefined) {
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export function asJsonString(value: unknown) {
  if (value === null || value === undefined) return null;
  return JSON.stringify(value);
}
