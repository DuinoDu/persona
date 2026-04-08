import { spawn } from "node:child_process";
import type { InferHostJobConfig } from "./remoteJobs";

export function encodeSse(payload: unknown) {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function normalizeSseBuffer(buffer: string) {
  return buffer.replace(/\r\n/g, "\n");
}

export function parseSseBlocks(buffer: string) {
  const blocks: string[] = [];
  let rest = normalizeSseBuffer(buffer);
  while (true) {
    const boundary = rest.indexOf("\n\n");
    if (boundary < 0) {
      break;
    }
    blocks.push(rest.slice(0, boundary));
    rest = rest.slice(boundary + 2);
  }
  return { blocks, rest };
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

export type RemoteSseEvent =
  | { kind: "payload"; payload: Record<string, unknown> }
  | { kind: "stderr"; chunk: string }
  | { kind: "exit"; code: number | null; stderr: string };

export async function* streamRemoteSseOverSsh(input: {
  host: Pick<InferHostJobConfig, "sshHost" | "sshPort" | "sshUser">;
  remoteCommand: string;
  signal?: AbortSignal | null;
}): AsyncGenerator<RemoteSseEvent> {
  const child = spawn("ssh", [
    "-p",
    String(input.host.sshPort),
    `${input.host.sshUser}@${input.host.sshHost}`,
    input.remoteCommand,
  ]);

  if (child.stdout === null || child.stderr === null) {
    child.kill("SIGTERM");
    throw new Error("远端流式 ssh 未提供 stdout/stderr 管道");
  }

  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");

  let stdoutBuffer = "";
  let stderrBuffer = "";
  let closed = false;
  let terminalError: Error | null = null;
  let wake: (() => void) | null = null;
  const queue: RemoteSseEvent[] = [];

  const push = (event: RemoteSseEvent) => {
    queue.push(event);
    wake?.();
    wake = null;
  };

  const flushStdout = () => {
    const parsed = parseSseBlocks(stdoutBuffer);
    stdoutBuffer = parsed.rest;
    for (const block of parsed.blocks) {
      const payload = parseSsePayload(block);
      if (payload) {
        push({ kind: "payload", payload });
      }
    }
  };

  child.stdout.on("data", (chunk: string) => {
    stdoutBuffer += chunk;
    flushStdout();
  });

  child.stderr.on("data", (chunk: string) => {
    stderrBuffer += chunk;
    push({ kind: "stderr", chunk });
  });

  child.on("error", (error) => {
    terminalError = error;
    closed = true;
    wake?.();
    wake = null;
  });

  child.on("close", (code) => {
    flushStdout();
    push({ kind: "exit", code, stderr: stderrBuffer.trim() });
    closed = true;
    wake?.();
    wake = null;
  });

  const abort = () => {
    child.kill("SIGTERM");
  };
  input.signal?.addEventListener("abort", abort);

  try {
    while (!closed || queue.length > 0) {
      if (queue.length === 0) {
        await new Promise<void>((resolve) => {
          wake = resolve;
        });
      }
      while (queue.length > 0) {
        yield queue.shift() as RemoteSseEvent;
      }
      if (terminalError) {
        throw terminalError;
      }
    }
  } finally {
    input.signal?.removeEventListener("abort", abort);
    child.kill("SIGTERM");
  }
}
