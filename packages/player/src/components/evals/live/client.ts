import { asRecord, asString } from "./types";

export class ApiError extends Error {
  payload: unknown;

  constructor(message: string, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.payload = payload;
  }
}

export function extractErrorPayload(error: unknown) {
  return error instanceof ApiError ? error.payload : null;
}

export async function readJson(response: Response) {
  return response.json().catch(() => ({}));
}

export function parseSsePayload(block: string) {
  const dataLines = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) {
    return null;
  }
  try {
    return JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function postJson(path: string, payload: unknown) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJson(response);
  if (response.ok === false) {
    throw new ApiError(asString(asRecord(data)?.error) || "请求失败", data);
  }
  return data;
}

export async function getJson(path: string) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await readJson(response);
  if (response.ok === false) {
    throw new ApiError(asString(asRecord(data)?.error) || "请求失败", data);
  }
  return data;
}

export async function postSse(
  path: string,
  payload: unknown,
  onEvent: (event: Record<string, unknown>) => void
) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.ok === false) {
    const data = await readJson(response);
    throw new ApiError(asString(asRecord(data)?.error) || "请求失败", data);
  }
  if (!response.body) {
    throw new Error("流式响应不可用");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    while (true) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary < 0) {
        break;
      }
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsedPayload = parseSsePayload(block);
      if (parsedPayload) {
        onEvent(parsedPayload);
      }
    }
  }
}
