import fs from "node:fs";
import path from "node:path";
import { resolveFeedbackTargetForAudio } from "../subtitleSegments";
import { getDefaultPartsRoot, getDefaultRawTextsRoot } from "../runtimePaths";
import {
  asOptionalInt,
  asOptionalNumber,
  asOptionalString,
  asString,
  type JsonServiceResult,
  jsonResult,
  type ProcessDbClient,
} from "./shared";

const PROMPT_VERSION = "2026-03-25.v2";

function escapeCsvValue(value: unknown) {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function atomicWriteJson(filePath: string, data: unknown) {
  const tmpPath = `${filePath}.tmp`;
  fs.writeFileSync(tmpPath, `${JSON.stringify(data, null, 2)}\n`, "utf-8");
  fs.renameSync(tmpPath, filePath);
}

function resolveTranscriptsDir(rawTextsDir: string) {
  if (process.env.RAW_TRANSCRIPTS_DIR) {
    return process.env.RAW_TRANSCRIPTS_DIR;
  }

  const normalized = path.resolve(rawTextsDir);
  return normalized.replace(
    `${path.sep}04_conversations_v2${path.sep}`,
    `${path.sep}03_transcripts${path.sep}`
  );
}

function isPathWithinRoot(filePath: string, rootPath: string) {
  const relative = path.relative(rootPath, filePath);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function getAllowedSubtitleRoots() {
  const roots = new Set<string>();
  const addRoot = (candidate?: string | null) => {
    if (!candidate) return;
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved)) {
      roots.add(resolved);
    }
  };

  const explicitRoots = String(process.env.FEEDBACK_REPAIR_ALLOWED_SUBTITLE_ROOTS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  explicitRoots.forEach(addRoot);

  const rawTextsDir = process.env.RAW_TEXTS_DIR || getDefaultRawTextsRoot();
  addRoot(resolveTranscriptsDir(rawTextsDir));
  addRoot(process.env.RAW_TRANSCRIPTS_DIR);
  addRoot(process.env.PARTS_ROOT_DIR || getDefaultPartsRoot());

  return [...roots];
}

function assertSafeSubtitleSourcePath(sourcePath: string) {
  const resolvedPath = path.resolve(sourcePath);
  const allowedRoots = getAllowedSubtitleRoots();
  if (allowedRoots.some((root) => resolvedPath === root || isPathWithinRoot(resolvedPath, root))) {
    return resolvedPath;
  }
  throw new Error(`字幕源路径不在允许目录内: ${resolvedPath}`);
}

interface RepairPatchChange {
  sourceIndex?: number | null;
  before?: string | null;
  after?: string | null;
}

interface RepairPatch {
  sourcePath?: string | null;
  sourceKind?: string | null;
  changes?: RepairPatchChange[];
}

export async function createFeedbackService(input: {
  db: ProcessDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const audioFilename = asString(body.audioFilename);
  const subtitleId = asString(body.subtitleId);
  const submittedSubtitleFile = asString(body.subtitleFile);
  const message = asString(body.message);
  const subtitleText = asString(body.subtitleText);
  const subtitleIndex = asOptionalInt(body.subtitleIndex);
  const subtitleStart = asOptionalNumber(body.subtitleStart);
  const subtitleEnd = asOptionalNumber(body.subtitleEnd);

  if (!subtitleText || !audioFilename || !message) {
    return jsonResult({ error: "Missing required fields" }, 400);
  }

  let resolvedTarget;
  try {
    resolvedTarget = resolveFeedbackTargetForAudio({
      audioFilename,
      subtitleId,
      subtitleIndex,
      subtitleText,
      subtitleStart,
      subtitleEnd,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: errorMessage }, 400);
  }

  const subtitleFile = submittedSubtitleFile || audioFilename.replace(/\.mp3$/i, ".json");
  const result = await input.db.$transaction(async (tx: ProcessDbClient) => {
    const feedback = await tx.feedback.create({
      data: {
        audioId: asOptionalString(body.audioId),
        audioFilename,
        audioDate: asOptionalString(body.audioDate),
        audioPersonTag: asOptionalString(body.audioPersonTag),
        audioStartTime: asOptionalString(body.audioStartTime),
        audioEndTime: asOptionalString(body.audioEndTime),
        subtitleFile,
        subtitleIndex,
        subtitleStart: resolvedTarget.start,
        subtitleEnd: resolvedTarget.end,
        subtitleText: resolvedTarget.text,
        subtitleSourceKind: resolvedTarget.sourceKind,
        subtitleSourcePath: resolvedTarget.sourcePath,
        subtitleSourceIndex: resolvedTarget.sourceIndex,
        subtitleAbsStart: resolvedTarget.absStart,
        subtitleAbsEnd: resolvedTarget.absEnd,
        message,
        processingStatus: "待处理",
        repairStatus: "pending",
      },
    });

    const job = await tx.feedbackRepairJob.create({
      data: {
        feedbackId: feedback.id,
        status: "pending",
        promptVersion: PROMPT_VERSION,
      },
    });

    return { feedback, job };
  });

  return jsonResult(result);
}

export async function revertFeedbackService(input: {
  db: ProcessDbClient;
  feedbackId: string;
}) {
  const feedback = await input.db.feedback.findUnique({
    where: { id: input.feedbackId },
    select: {
      id: true,
      repairStatus: true,
      repairSummary: true,
      repairPatchJson: true,
      subtitleSourcePath: true,
      subtitleSourceKind: true,
    },
  });

  if (!feedback) {
    return jsonResult({ error: "Feedback not found" }, 404);
  }

  if (!feedback.repairPatchJson) {
    return jsonResult({ error: "该修复没有可撤销的 patch" }, 400);
  }

  let patch: RepairPatch;
  try {
    patch = JSON.parse(feedback.repairPatchJson) as RepairPatch;
  } catch {
    return jsonResult({ error: "修复 patch 已损坏，无法撤销" }, 400);
  }

  let sourcePath: string;
  try {
    sourcePath = assertSafeSubtitleSourcePath(patch.sourcePath || feedback.subtitleSourcePath || "");
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: errorMessage }, 400);
  }
  const sourceKind = patch.sourceKind || feedback.subtitleSourceKind;
  const collectionKey = sourceKind === "sentences" ? "sentences" : "segments";
  const changes = Array.isArray(patch.changes) ? patch.changes : [];

  if (changes.length === 0) {
    return jsonResult({ error: "修复 patch 不包含可撤销的变更" }, 400);
  }

  if (!fs.existsSync(sourcePath)) {
    return jsonResult({ error: "原始字幕文件不存在" }, 404);
  }

  const doc = JSON.parse(fs.readFileSync(sourcePath, "utf-8")) as Record<string, unknown>;
  const items = Array.isArray(doc[collectionKey]) ? (doc[collectionKey] as Array<Record<string, unknown>>) : null;
  if (!items) {
    return jsonResult({ error: `字幕文件缺少数组字段: ${collectionKey}` }, 400);
  }

  let alreadyReverted = true;
  for (const change of changes) {
    const sourceIndex = typeof change.sourceIndex === "number" ? change.sourceIndex : null;
    if (sourceIndex == null || sourceIndex < 0 || sourceIndex >= items.length) {
      return jsonResult({ error: "patch 中的字幕索引无效，无法撤销" }, 400);
    }
    const item = items[sourceIndex];
    const currentText = typeof item.text === "string" ? item.text : null;
    if (currentText == null) {
      return jsonResult({ error: "当前字幕内容缺失，无法撤销" }, 400);
    }
    if (currentText !== change.before) {
      alreadyReverted = false;
      if (currentText !== change.after) {
        return jsonResult({ error: "当前字幕内容已变化，无法安全撤销，请人工处理" }, 409);
      }
    }
  }

  if (!alreadyReverted) {
    for (const change of changes) {
      const sourceIndex = change.sourceIndex as number;
      const item = items[sourceIndex];
      item.text = change.before ?? "";
    }
    atomicWriteJson(sourcePath, doc);
  }

  const now = new Date();
  await input.db.feedback.update({
    where: { id: feedback.id },
    data: {
      repairStatus: "reverted",
      processingStatus: "已处理",
      repairSummary: feedback.repairSummary
        ? `已撤销修复 · ${feedback.repairSummary}`
        : "已撤销修复",
      repairedText: null,
      repairedAt: null,
      processedAt: now,
      repairError: null,
    },
  });

  return jsonResult({ ok: true, alreadyReverted });
}

export async function exportFeedbackCsvService(input: {
  db: ProcessDbClient;
}) {
  const feedbacks = await input.db.feedback.findMany({
    orderBy: { createdAt: "desc" },
  });

  const headers = [
    "id",
    "createdAt",
    "audioId",
    "audioFilename",
    "audioDate",
    "audioPersonTag",
    "audioStartTime",
    "audioEndTime",
    "subtitleFile",
    "subtitleIndex",
    "subtitleStart",
    "subtitleEnd",
    "subtitleText",
    "subtitleSourceKind",
    "subtitleSourcePath",
    "subtitleSourceIndex",
    "subtitleAbsStart",
    "subtitleAbsEnd",
    "message",
    "processingStatus",
    "processedAt",
    "repairStatus",
    "repairSummary",
    "repairConfidence",
    "repairedText",
    "repairPatchJson",
    "repairError",
    "repairedAt",
  ];

  const rows = feedbacks.map((item: Record<string, any>) => [
    item.id,
    item.createdAt.toISOString(),
    item.audioId,
    item.audioFilename,
    item.audioDate,
    item.audioPersonTag,
    item.audioStartTime,
    item.audioEndTime,
    item.subtitleFile,
    item.subtitleIndex,
    item.subtitleStart,
    item.subtitleEnd,
    item.subtitleText,
    item.subtitleSourceKind,
    item.subtitleSourcePath,
    item.subtitleSourceIndex,
    item.subtitleAbsStart,
    item.subtitleAbsEnd,
    item.message,
    item.processingStatus,
    item.processedAt?.toISOString(),
    item.repairStatus,
    item.repairSummary,
    item.repairConfidence,
    item.repairedText,
    item.repairPatchJson,
    item.repairError,
    item.repairedAt?.toISOString(),
  ]);

  const csv = `\uFEFF${[headers, ...rows]
    .map((row) => row.map(escapeCsvValue).join(","))
    .join("\n")}`;

  return {
    csv,
    filename: "feedback-export.csv",
  };
}
