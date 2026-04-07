import { promises as fs } from "node:fs";
import * as path from "node:path";

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

export async function loadGenerationRecords(outputDir: string | null | undefined) {
  if (!outputDir) {
    return [] as GenerationRecord[];
  }

  const filePath = path.join(outputDir, "generations.jsonl");
  let text = "";
  try {
    text = await fs.readFile(filePath, "utf-8");
  } catch {
    return [] as GenerationRecord[];
  }

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
