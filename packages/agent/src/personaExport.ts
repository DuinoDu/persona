import { promises as fs } from "node:fs";
import * as path from "node:path";
import { GenerationRecord } from "./evalArtifacts";

export type PersonaExportSourceType = "offline_case" | "live_turn" | "arena_pair";
export type PersonaExportRecordType = "sft_candidate" | "preference_pair_candidate";
export type PersonaExportMode = "auto" | PersonaExportRecordType;

export interface PersonaExportMessage {
  role: string;
  content: string;
}

export interface PersonaExportOverride {
  inputMessages?: PersonaExportMessage[];
  modelOutput?: string;
  editedTargetText?: string;
  chosenText?: string;
  rejectedText?: string;
  tracePath?: string;
  sourcePath?: string;
  notes?: string;
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asOptionalString(value: unknown) {
  const text = asString(value).trim();
  return text.length > 0 ? text : null;
}

function asMessageList(value: unknown): PersonaExportMessage[] {
  const items = Array.isArray(value) ? value : [];
  const messages: PersonaExportMessage[] = [];
  for (const item of items) {
    const record = asRecord(item);
    if (!record) continue;
    const role = asString(record.role).trim();
    const content = asString(record.content);
    if (!role || !content) continue;
    messages.push({ role, content });
  }
  return messages;
}

function parseJsonMaybe(value: unknown) {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function parseIsoDateTime(date = new Date()) {
  return date.toISOString();
}

function formatYYYYMMDD(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(date)
    .replace(/-/g, "");
}

function resolveWorkspaceRoot() {
  const cwd = process.cwd();
  const base = path.basename(cwd);
  const parent = path.basename(path.dirname(cwd));
  if ((base === "player" || base === "agent") && parent === "packages") {
    return path.resolve(cwd, "../..");
  }
  if (base === "player" || base === "agent") {
    return path.resolve(cwd, "..");
  }
  return cwd;
}

function resolveExportId(date = new Date()) {
  const stamp = date
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "Z")
    .replace("T", "_")
    .slice(0, 15);
  const short = Math.random().toString(36).slice(2, 7);
  return `export_${stamp}_${short}`;
}

export function buildPersonaExportPaths(exportId: string, date = new Date()) {
  const workspaceRoot = resolveWorkspaceRoot();
  const day = formatYYYYMMDD(date);
  const outputDir = path.join(workspaceRoot, "artifacts", "evals", "exports", day);
  const jsonlPath = path.join(outputDir, `${exportId}.jsonl`);
  const manifestPath = path.join(outputDir, "manifest.json");
  const readmePath = path.join(outputDir, "README.md");
  return {
    workspaceRoot,
    outputDir,
    jsonlPath,
    manifestPath,
    readmePath,
  };
}

function buildAnnotationVersion() {
  return "annotation_v1";
}

function buildSourceBase(input: {
  sourceType: PersonaExportSourceType;
  sourceId: string | null;
  modelId: string | null;
  deploymentId: string | null;
  runId: string | null;
  liveSessionId: string | null;
  liveTurnId: string | null;
  caseId: string | null;
  slice: string | null;
  promptVersion: string | null;
  contextBuilderVersion: string | null;
  generationConfigVersion: string | null;
}) {
  return {
    source_type: input.sourceType,
    source_id: input.sourceId,
    project: "ququ_youtube",
    annotation_version: buildAnnotationVersion(),
    model_id: input.modelId,
    deployment_id: input.deploymentId,
    run_id: input.runId,
    live_session_id: input.liveSessionId,
    live_turn_id: input.liveTurnId,
    case_id: input.caseId,
    slice: input.slice,
    prompt_version: input.promptVersion,
    context_builder_version: input.contextBuilderVersion,
    generation_config_version: input.generationConfigVersion,
  };
}

function deriveMessagesFromGenerationRecord(record: GenerationRecord | null | undefined) {
  return record?.messages || [];
}

function deriveMessagesFromTrace(trace: Record<string, unknown> | null | undefined) {
  if (!trace) return [];
  const request = asRecord(trace.request);
  const messages = request ? asMessageList(request.messages) : [];
  if (messages.length > 0) return messages;
  const parsed = parseJsonMaybe(trace.finalMessagesJson);
  return asMessageList(parsed);
}

function deriveModelOutputFromTrace(trace: Record<string, unknown> | null | undefined) {
  if (!trace) return "";
  const response = asRecord(trace.response);
  const outputText = asOptionalString(response?.output_text);
  if (outputText) return outputText;
  const outputFromTop = asOptionalString(trace.outputText);
  if (outputFromTop) return outputFromTop;
  const rawOutputJson = asRecord(trace.rawOutputJson);
  const rawOutputText = asOptionalString(rawOutputJson?.output_text);
  return rawOutputText || "";
}

function buildGenerationConfigSnapshot(input: {
  runtimeSignature: Record<string, unknown> | null;
  generation: Record<string, unknown> | null;
  trace: Record<string, unknown> | null;
}) {
  return {
    runtime_signature: input.runtimeSignature,
    generation: input.generation,
    trace_meta: input.trace ? asRecord(input.trace.traceMetaJson) : null,
  };
}

export interface BuildSftCandidateInput {
  badCase: Record<string, unknown>;
  sourceType: PersonaExportSourceType;
  inputMessages: PersonaExportMessage[];
  modelOutput: string;
  editedTargetText: string;
  runtimeSignature: Record<string, unknown> | null;
  generationConfig: Record<string, unknown> | null;
  trace: Record<string, unknown> | null;
  tracePath?: string | null;
  sourcePath?: string | null;
  annotatorId?: string | null;
  reviewerId?: string | null;
}

export interface BuildPreferencePairInput {
  badCase: Record<string, unknown>;
  sourceType: PersonaExportSourceType;
  contextMessages: PersonaExportMessage[];
  chosenText: string;
  rejectedText: string;
  runtimeSignature: Record<string, unknown> | null;
  generationConfig: Record<string, unknown> | null;
  trace: Record<string, unknown> | null;
  tracePath?: string | null;
  sourcePath?: string | null;
  annotatorId?: string | null;
  reviewerId?: string | null;
}

export function buildSftCandidateRecord(input: BuildSftCandidateInput) {
  const badCase = input.badCase;
  const caseId = asOptionalString(badCase.caseId);
  const sourceId = asOptionalString(badCase.sourceId) || caseId || null;
  const source = buildSourceBase({
    sourceType: input.sourceType,
    sourceId,
    modelId: asOptionalString(badCase.modelDeploymentId),
    deploymentId: asOptionalString(badCase.modelDeploymentId),
    runId: asOptionalString(badCase.evalRunId),
    liveSessionId: asOptionalString(badCase.liveSessionId),
    liveTurnId: asOptionalString(badCase.liveTurnId),
    caseId,
    slice: asOptionalString(badCase.sourceSlice) || asOptionalString(badCase.slice) || null,
    promptVersion: asOptionalString(input.runtimeSignature?.prompt_version) || null,
    contextBuilderVersion: asOptionalString(input.runtimeSignature?.context_builder_version) || null,
    generationConfigVersion: asOptionalString(input.runtimeSignature?.generation_config_version) || null,
  });

  return {
    record_type: "sft_candidate",
    version: "export_v1",
    candidate_id: asOptionalString(badCase.id) || `${sourceId || "case"}_sft`,
    source,
    input_messages: input.inputMessages,
    model_output: input.modelOutput,
    edited_target: input.editedTargetText,
    labels: {
      failure_tags: Array.isArray(parseJsonMaybe(badCase.failureTagsJson))
        ? (parseJsonMaybe(badCase.failureTagsJson) as unknown[]).map((item) => asString(item)).filter(Boolean)
        : [],
      topic_primary: asOptionalString(badCase.topicPrimary),
      difficulty: asOptionalString(badCase.difficulty),
      reply_type: asOptionalString(badCase.replyType),
    },
    metadata: {
      source_path: input.sourcePath || null,
      trace_path: input.tracePath || null,
      prompt_tokens: input.trace ? Number(input.trace.promptTokens ?? input.trace.estimatedPromptTokens ?? 0) || 0 : 0,
      generated_tokens: input.trace ? Number(input.trace.generatedTokens ?? 0) || 0 : 0,
      latency_ms: input.trace ? Number(input.trace.totalLatencyMs ?? input.trace.firstTokenLatencyMs ?? 0) || 0 : 0,
      annotator_id: input.annotatorId || null,
      reviewer_id: input.reviewerId || null,
      created_at: parseIsoDateTime(),
      notes: asOptionalString(input.badCase.notes),
    },
  };
}

export function buildPreferencePairRecord(input: BuildPreferencePairInput) {
  const badCase = input.badCase;
  const caseId = asOptionalString(badCase.caseId);
  const sourceId = asOptionalString(badCase.sourceId) || caseId || null;
  const source = buildSourceBase({
    sourceType: input.sourceType,
    sourceId,
    modelId: asOptionalString(badCase.modelDeploymentId),
    deploymentId: asOptionalString(badCase.modelDeploymentId),
    runId: asOptionalString(badCase.evalRunId),
    liveSessionId: asOptionalString(badCase.liveSessionId),
    liveTurnId: asOptionalString(badCase.liveTurnId),
    caseId,
    slice: asOptionalString(badCase.sourceSlice) || asOptionalString(badCase.slice) || null,
    promptVersion: asOptionalString(input.runtimeSignature?.prompt_version) || null,
    contextBuilderVersion: asOptionalString(input.runtimeSignature?.context_builder_version) || null,
    generationConfigVersion: asOptionalString(input.runtimeSignature?.generation_config_version) || null,
  });

  return {
    record_type: "preference_pair_candidate",
    version: "export_v1",
    pair_id: asOptionalString(badCase.id) || `${sourceId || "case"}_pair`,
    source,
    context_messages: input.contextMessages,
    chosen: {
      candidate_id: "cand_a",
      provenance: "human",
      text: input.chosenText,
    },
    rejected: {
      candidate_id: "cand_b",
      provenance: "model",
      text: input.rejectedText,
    },
    judgement: {
      winner: "chosen",
      preference_strength: "medium",
      reason_tags: [],
      scores: {},
    },
    metadata: {
      source_path: input.sourcePath || null,
      trace_path: input.tracePath || null,
      annotator_id: input.annotatorId || null,
      reviewer_id: input.reviewerId || null,
      created_at: parseIsoDateTime(),
      notes: asOptionalString(input.badCase.notes),
    },
  };
}

export function normalizeExportMode(mode: unknown): PersonaExportMode {
  const value = asString(mode);
  if (value === "sft_candidate" || value === "preference_pair_candidate") {
    return value;
  }
  return "auto";
}

export function resolveExportRecordType(
  mode: PersonaExportMode,
  badCase: Record<string, unknown>,
  override?: PersonaExportOverride | null
) {
  if (mode === "sft_candidate") return "sft_candidate" as const;
  if (mode === "preference_pair_candidate") return "preference_pair_candidate" as const;
  const editedTarget = asOptionalString(override?.editedTargetText) || asOptionalString(badCase.editedTargetText);
  const chosenText = asOptionalString(override?.chosenText) || asOptionalString(badCase.chosenText);
  const rejectedText = asOptionalString(override?.rejectedText) || asOptionalString(badCase.rejectedText);
  if (editedTarget) return "sft_candidate" as const;
  if (chosenText && rejectedText) return "preference_pair_candidate" as const;
  return null;
}

export function resolveFailureTags(badCase: Record<string, unknown>) {
  const parsed = parseJsonMaybe(badCase.failureTagsJson);
  if (!Array.isArray(parsed)) return [];
  return parsed.map((item) => asString(item)).filter(Boolean);
}

export function resolveRubricScores(badCase: Record<string, unknown>) {
  const parsed = parseJsonMaybe(badCase.rubricScoresJson);
  return parsed && typeof parsed === "object" ? parsed : {};
}

export function resolveTraceSnapshot(
  badCase: Record<string, unknown>,
  trace: Record<string, unknown> | null,
  generationRecord: GenerationRecord | null
) {
  const runtimeSignature = trace ? asRecord(parseJsonMaybe(trace.runtimeSignatureJson)) : null;
  const generationConfig = trace ? asRecord(parseJsonMaybe(trace.generationConfigJson)) : null;
  const traceMessages = deriveMessagesFromTrace(trace);
  const inputMessages = traceMessages.length > 0 ? traceMessages : deriveMessagesFromGenerationRecord(generationRecord);
  const modelOutput =
    deriveModelOutputFromTrace(trace) ||
    generationRecord?.cleanOutputText ||
    generationRecord?.rawOutputText ||
    "";
  return {
    runtimeSignature,
    generationConfig,
    inputMessages,
    modelOutput,
    sourcePath: asOptionalString(trace?.remoteArtifactPath) || asOptionalString(badCase.sourcePath),
  };
}

export async function materializeExportBundle(input: {
  exportId: string;
  title: string;
  recordTypes: PersonaExportRecordType[];
  records: unknown[];
}) {
  const now = new Date();
  const paths = buildPersonaExportPaths(input.exportId, now);
  await fs.mkdir(paths.outputDir, { recursive: true });

  const jsonl = `${input.records.map((record) => JSON.stringify(record)).join("\n")}\n`;
  await fs.writeFile(paths.jsonlPath, jsonl, "utf-8");

  const manifest = {
    export_id: input.exportId,
    version: "export_v1",
    title: input.title,
    created_at: now.toISOString(),
    source_types: Array.from(
      new Set(
        input.records
          .map((record) => asRecord(record)?.source)
          .map((source) => asRecord(source))
          .map((source) => asOptionalString(source?.source_type))
          .filter((item): item is string => Boolean(item))
      )
    ),
    record_count: input.records.length,
    record_types: input.recordTypes,
    jsonl_path: paths.jsonlPath,
  };
  await fs.writeFile(paths.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");

  const readme = [
    `# ${input.title}`,
    "",
    `- export_id: ${input.exportId}`,
    `- created_at: ${manifest.created_at}`,
    `- record_count: ${manifest.record_count}`,
    `- record_types: ${manifest.record_types.join(", ")}`,
    `- jsonl: ${paths.jsonlPath}`,
    `- manifest: ${paths.manifestPath}`,
  ].join("\n");
  await fs.writeFile(paths.readmePath, `${readme}\n`, "utf-8");

  return {
    ...paths,
    manifest,
  };
}

export function createExportId(date = new Date()) {
  return resolveExportId(date);
}
