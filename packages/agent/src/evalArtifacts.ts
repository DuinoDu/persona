import { promises as fs } from "node:fs";
import * as path from "node:path";
import { InferHostJobConfig, remoteReadTextFile } from "./remoteJobs";

export interface EvalMessage {
  role: string;
  content: string;
}

export interface GenerationRecord {
  id: string;
  slice: string;
  tags: string[];
  messages: EvalMessage[];
  promptTokens: number;
  generatedTokens: number;
  latencyMs: number;
  rawOutputText: string;
  cleanOutputText: string;
  outputCharLen: number;
  blankOutput: boolean;
  shortOutput: boolean;
  containsControlTokens: boolean;
  runtimeSignature?: Record<string, unknown> | null;
  generation?: Record<string, unknown> | null;
  tracePath?: string | null;
}

export interface ArenaOutputSlot {
  runId: string;
  outputText: string;
  rawOutputText: string;
  generatedTokens: number;
  latencyMs: number;
  blankOutput: boolean;
  shortOutput: boolean;
  containsControlTokens: boolean;
}

export interface ArenaCaseComparison {
  caseId: string;
  caseSlice: string;
  promptPreview: string;
  messages: EvalMessage[];
  left: GenerationRecord;
  right: GenerationRecord;
  slotA: ArenaOutputSlot;
  slotB: ArenaOutputSlot;
}

export interface RemoteReadableRun {
  outputDir?: string | null;
  summaryPath?: string | null;
  inferHost?: InferHostJobConfig | null;
}

export interface BatchCaseTraceRecord {
  kind: string;
  request_id: string;
  case_id: string;
  slice: string;
  tags: string[];
  runtime_signature: Record<string, unknown>;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
  metrics: Record<string, unknown>;
  artifacts: Record<string, unknown>;
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asBoolean(value: unknown) {
  return value === true;
}

function normalizeMessage(value: unknown): EvalMessage | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const role = asString(record.role);
  const content = asString(record.content);
  if (!role) {
    return null;
  }
  return { role, content };
}

function normalizeGenerationRecord(value: unknown): GenerationRecord | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const messagesRaw = Array.isArray(record.messages) ? record.messages : [];
  const messages = messagesRaw.map(normalizeMessage).filter((item): item is EvalMessage => item !== null);
  const id = asString(record.id);
  if (!id) {
    return null;
  }

  const tags = Array.isArray(record.tags) ? record.tags.map((item) => asString(item)).filter(Boolean) : [];
  return {
    id,
    slice: asString(record.slice) || "unspecified",
    tags,
    messages,
    promptTokens: asNumber(record.prompt_tokens),
    generatedTokens: asNumber(record.generated_tokens),
    latencyMs: asNumber(record.latency_ms),
    rawOutputText: asString(record.raw_output_text),
    cleanOutputText: asString(record.clean_output_text),
    outputCharLen: asNumber(record.output_char_len),
    blankOutput: asBoolean(record.blank_output),
    shortOutput: asBoolean(record.short_output),
    containsControlTokens: asBoolean(record.contains_control_tokens),
    runtimeSignature: asRecord(record.runtime_signature),
    generation: asRecord(record.generation),
    tracePath: asString(record.trace_path) || null,
  };
}

function stableHash(seed: string) {
  let hash = 2166136261;
  for (const ch of seed) {
    hash ^= ch.charCodeAt(0);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

function toArenaSlot(runId: string, record: GenerationRecord): ArenaOutputSlot {
  return {
    runId,
    outputText: record.cleanOutputText,
    rawOutputText: record.rawOutputText,
    generatedTokens: record.generatedTokens,
    latencyMs: record.latencyMs,
    blankOutput: record.blankOutput,
    shortOutput: record.shortOutput,
    containsControlTokens: record.containsControlTokens,
  };
}

function parseGenerationRecordsText(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return normalizeGenerationRecord(JSON.parse(line));
      } catch {
        return null;
      }
    })
    .filter((item): item is GenerationRecord => item !== null);
}

async function readTextFileMaybeRemote(filePath: string, inferHost?: InferHostJobConfig | null) {
  try {
    return await fs.readFile(filePath, "utf-8");
  } catch {
    if (!inferHost) {
      return null;
    }
    try {
      return await remoteReadTextFile({
        host: inferHost,
        filePath,
      });
    } catch {
      return null;
    }
  }
}

export async function loadGenerationRecords(outputDir: string | null | undefined) {
  if (!outputDir) {
    return [] as GenerationRecord[];
  }

  const text = await readTextFileMaybeRemote(path.join(outputDir, "generations.jsonl"), null);
  if (!text) {
    return [] as GenerationRecord[];
  }
  return parseGenerationRecordsText(text);
}

export async function loadGenerationRecordsFromRun(run: RemoteReadableRun) {
  if (!run.outputDir) {
    return [] as GenerationRecord[];
  }
  const text = await readTextFileMaybeRemote(
    path.join(run.outputDir, "generations.jsonl"),
    run.inferHost || null
  );
  if (!text) {
    return [] as GenerationRecord[];
  }
  return parseGenerationRecordsText(text);
}

export function buildBatchTraceViewerId(runId: string, caseId: string) {
  return `${runId}::${encodeURIComponent(caseId)}`;
}

export function parseBatchTraceViewerId(value: string) {
  const separator = value.indexOf("::");
  if (separator < 0) {
    return null;
  }
  const runId = value.slice(0, separator).trim();
  const encodedCaseId = value.slice(separator + 2).trim();
  if (!runId || !encodedCaseId) {
    return null;
  }
  try {
    return {
      runId,
      caseId: decodeURIComponent(encodedCaseId),
    };
  } catch {
    return null;
  }
}

export function buildBatchTracePath(outputDir: string, caseId: string) {
  return path.join(outputDir, "traces", `${caseId}.json`);
}

function normalizeBatchTraceRecord(value: unknown): BatchCaseTraceRecord | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const runtimeSignature = asRecord(record.runtime_signature);
  const request = asRecord(record.request);
  const response = asRecord(record.response);
  const metrics = asRecord(record.metrics);
  const artifacts = asRecord(record.artifacts);
  const requestId = asString(record.request_id);
  const caseId = asString(record.case_id);
  if (!requestId || !caseId || !runtimeSignature || !request || !response || !metrics || !artifacts) {
    return null;
  }

  return {
    kind: asString(record.kind) || "persona_batch_case_trace_v1",
    request_id: requestId,
    case_id: caseId,
    slice: asString(record.slice) || "unspecified",
    tags: Array.isArray(record.tags) ? record.tags.map((item) => asString(item)).filter(Boolean) : [],
    runtime_signature: runtimeSignature,
    request,
    response,
    metrics,
    artifacts,
  };
}

async function readBatchTraceTextFromRun(run: RemoteReadableRun, caseId: string) {
  if (!run.outputDir) {
    return null;
  }
  return readTextFileMaybeRemote(buildBatchTracePath(run.outputDir, caseId), run.inferHost || null);
}

export async function loadBatchTraceFromRun(run: RemoteReadableRun, caseId: string) {
  const text = await readBatchTraceTextFromRun(run, caseId);
  if (!text) {
    return null;
  }
  try {
    return normalizeBatchTraceRecord(JSON.parse(text));
  } catch {
    return null;
  }
}

export async function loadSummaryJsonTextFromRun(run: RemoteReadableRun) {
  if (!run.summaryPath) {
    return null;
  }
  const text = await readTextFileMaybeRemote(run.summaryPath, run.inferHost || null);
  return text || null;
}

export function buildPromptPreview(messages: EvalMessage[]) {
  const lastUser = [...messages].reverse().find((message) => message.role === "user");
  const text = (lastUser?.content || messages[messages.length - 1]?.content || "").trim();
  if (text.length <= 160) {
    return text;
  }
  return text.slice(0, 157) + "...";
}

export function stableBlindLeftIsSlotA(leftRunId: string, rightRunId: string, caseId: string) {
  return (stableHash(`${leftRunId}:${rightRunId}:${caseId}`) & 1) === 0;
}

export function buildArenaComparisons(input: {
  leftRunId: string;
  rightRunId: string;
  leftRecords: GenerationRecord[];
  rightRecords: GenerationRecord[];
}) {
  const rightByCaseId = new Map(input.rightRecords.map((record) => [record.id, record]));
  const items: ArenaCaseComparison[] = [];

  for (const left of input.leftRecords) {
    const right = rightByCaseId.get(left.id);
    if (!right) {
      continue;
    }

    const leftIsSlotA = stableBlindLeftIsSlotA(input.leftRunId, input.rightRunId, left.id);
    items.push({
      caseId: left.id,
      caseSlice: left.slice || right.slice || "unspecified",
      promptPreview: buildPromptPreview(left.messages.length > 0 ? left.messages : right.messages),
      messages: left.messages.length > 0 ? left.messages : right.messages,
      left,
      right,
      slotA: leftIsSlotA ? toArenaSlot(input.leftRunId, left) : toArenaSlot(input.rightRunId, right),
      slotB: leftIsSlotA ? toArenaSlot(input.rightRunId, right) : toArenaSlot(input.leftRunId, left),
    });
  }

  return items.sort((a, b) => a.caseId.localeCompare(b.caseId));
}
