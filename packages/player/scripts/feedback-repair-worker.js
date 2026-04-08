#!/usr/bin/env node
require("dotenv/config");

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { PrismaClient } = require("@prisma/client");

const prisma = new PrismaClient();
const ROOT = process.cwd();
function findAncestorDir(startDir, predicate) {
  let current = path.resolve(startDir);
  while (true) {
    if (predicate(current)) return current;
    const parent = path.dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}
function isRepoRoot(dir) {
  return (
    fs.existsSync(path.join(dir, "data")) &&
    fs.existsSync(path.join(dir, "packages", "player", "package.json")) &&
    fs.existsSync(path.join(dir, "packages", "process", "package.json"))
  );
}
function isPlayerRoot(dir) {
  return (
    fs.existsSync(path.join(dir, "package.json")) &&
    fs.existsSync(path.join(dir, "next.config.ts")) &&
    fs.existsSync(path.join(dir, "src", "app", "page.tsx"))
  );
}
const REPO_ROOT =
  (process.env.QUQU_REPO_ROOT && path.resolve(process.env.QUQU_REPO_ROOT)) ||
  findAncestorDir(ROOT, isRepoRoot);
const PLAYER_ROOT =
  (process.env.QUQU_PLAYER_ROOT && path.resolve(process.env.QUQU_PLAYER_ROOT)) ||
  (REPO_ROOT ? path.join(REPO_ROOT, "packages", "player") : findAncestorDir(ROOT, isPlayerRoot) || ROOT);
const DATA_ROOT =
  (process.env.QUQU_DATA_ROOT && path.resolve(process.env.QUQU_DATA_ROOT)) ||
  (REPO_ROOT ? path.join(REPO_ROOT, "data") : path.resolve(PLAYER_ROOT, "..", "..", "data"));
const WORKDIR = path.resolve(ROOT, process.env.FEEDBACK_REPAIR_WORKDIR || ".feedback-repair-work");
const POLL_MS = Number.parseInt(process.env.FEEDBACK_REPAIR_POLL_MS || "3000", 10);
const AUTO_APPLY_CONFIDENCE = Number.parseFloat(
  process.env.FEEDBACK_REPAIR_AUTO_APPLY_CONFIDENCE || "0.9"
);
const PROMPT_VERSION = "2026-03-25.v2";
const CODEX_BIN = process.env.FEEDBACK_REPAIR_CODEX_BIN || "codex";
const MODEL = process.env.FEEDBACK_REPAIR_MODEL || "";
const USE_OSS = String(process.env.FEEDBACK_REPAIR_USE_OSS || "false") === "true";
const LOCAL_PROVIDER = process.env.FEEDBACK_REPAIR_LOCAL_PROVIDER || "";
const RUN_ONCE = String(process.env.FEEDBACK_REPAIR_RUN_ONCE || "false") === "true";
const ENABLED = String(process.env.FEEDBACK_REPAIR_ENABLED || "true") !== "false";
const BIGMODEL_API_KEY =
  process.env.FEEDBACK_REPAIR_BIGMODEL_API_KEY ||
  process.env.BIGMODEL_API_KEY ||
  process.env.FEEDBACK_REPAIR_ZAI_API_KEY ||
  process.env.ZAI_API_KEY ||
  "";
const RAW_BIGMODEL_BASE_URL =
  process.env.FEEDBACK_REPAIR_BIGMODEL_BASE_URL ||
  process.env.BIGMODEL_BASE_URL ||
  process.env.FEEDBACK_REPAIR_ZAI_BASE_URL ||
  "https://open.bigmodel.cn/api/paas/v4";
const TRANSCRIBE_MODEL = process.env.FEEDBACK_REPAIR_TRANSCRIBE_MODEL || "glm-asr-2512";
const AUDIO_CLIP_PAD_SECONDS = Number.parseFloat(
  process.env.FEEDBACK_REPAIR_AUDIO_CLIP_PAD_SECONDS || "1.5"
);
const OUTPUT_SCHEMA_PATH = path.resolve(ROOT, "scripts/feedback-repair-output.schema.json");
const dirIndexCache = new Map();
let cachedAllowedSubtitleRoots = null;

let stopped = false;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function atomicWriteJson(filePath, data) {
  const tmpPath = `${filePath}.tmp`;
  fs.writeFileSync(tmpPath, `${JSON.stringify(data, null, 2)}\n`, "utf-8");
  fs.renameSync(tmpPath, filePath);
}

function sanitizeErrorMessage(message) {
  return String(message)
    .replace(/sk-[A-Za-z0-9_*.-]{8,}/g, "sk-***")
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer ***");
}

function normalizeBigModelBaseUrl(baseUrl) {
  const trimmed = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!trimmed) {
    return "https://open.bigmodel.cn/api/paas/v4";
  }
  if (trimmed.endsWith("/api/paas")) {
    return `${trimmed}/v4`;
  }
  return trimmed;
}

const BIGMODEL_BASE_URL = normalizeBigModelBaseUrl(RAW_BIGMODEL_BASE_URL);

function collectFilesRecursive(dir, files = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      collectFilesRecursive(fullPath, files);
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function getDirIndex(dir) {
  const resolvedDir = path.resolve(dir);
  if (!fs.existsSync(resolvedDir)) return null;

  const cached = dirIndexCache.get(resolvedDir);
  if (cached) return cached;

  const files = collectFilesRecursive(resolvedDir);
  const byName = new Map();
  for (const filePath of files) {
    const filename = path.basename(filePath);
    const list = byName.get(filename) || [];
    list.push(filePath);
    byName.set(filename, list);
  }

  const index = { files, byName };
  dirIndexCache.set(resolvedDir, index);
  return index;
}

function findFileCached(dir, filename) {
  const index = getDirIndex(dir);
  if (!index) return null;
  return index.byName.get(filename)?.[0] || null;
}

function resolveTranscriptsDir(rawTextsDir) {
  if (process.env.RAW_TRANSCRIPTS_DIR) {
    return process.env.RAW_TRANSCRIPTS_DIR;
  }

  const normalized = path.resolve(rawTextsDir);
  return normalized.replace(
    `${path.sep}04_conversations_v2${path.sep}`,
    `${path.sep}03_transcripts${path.sep}`
  );
}

function getAllowedSubtitleRoots() {
  if (cachedAllowedSubtitleRoots) {
    return cachedAllowedSubtitleRoots;
  }

  const roots = new Set();
  const addRoot = (candidate) => {
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

  const rawTextsDir =
    process.env.RAW_TEXTS_DIR || path.join(PLAYER_ROOT, "public", "audios", "raw_texts");
  addRoot(resolveTranscriptsDir(rawTextsDir));
  addRoot(process.env.RAW_TRANSCRIPTS_DIR);
  addRoot(process.env.PARTS_ROOT_DIR || path.join(DATA_ROOT, "03_parts"));

  const singleTranscriptFile = process.env.SINGLE_TRANSCRIPT_FILE;
  if (singleTranscriptFile) {
    addRoot(path.dirname(singleTranscriptFile));
  }

  const manifestFile = process.env.SINGLE_MANIFEST_FILE;
  if (manifestFile && fs.existsSync(manifestFile)) {
    try {
      const content = JSON.parse(fs.readFileSync(manifestFile, "utf-8"));
      const items = Array.isArray(content) ? content : content.items;
      if (Array.isArray(items)) {
        for (const item of items) {
          if (item?.subtitleJsonPath) {
            addRoot(path.dirname(item.subtitleJsonPath));
          }
        }
      }
    } catch {}
  }

  cachedAllowedSubtitleRoots = [...roots];
  return cachedAllowedSubtitleRoots;
}

function isPathWithinRoot(filePath, rootPath) {
  const relative = path.relative(rootPath, filePath);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function assertSafeSubtitleSourcePath(sourcePath) {
  const resolvedPath = path.resolve(sourcePath);
  const allowedRoots = getAllowedSubtitleRoots();
  if (allowedRoots.some((root) => resolvedPath === root || isPathWithinRoot(resolvedPath, root))) {
    return resolvedPath;
  }
  throw new Error(`字幕源路径不在允许目录内: ${resolvedPath}`);
}

function resolveAudioPath(feedback) {
  const filename = feedback.audioFilename;
  const rawAudiosDir =
    process.env.RAW_AUDIOS_DIR || path.join(DATA_ROOT, "01_downloads");

  const partAudioPath = resolvePartAudioPath(feedback, rawAudiosDir);
  if (partAudioPath) return partAudioPath;

  if (!filename) return null;

  const directPublicPath = path.join(PLAYER_ROOT, "public", "audios", "single", filename);
  if (fs.existsSync(directPublicPath)) return directPublicPath;

  const publicAudiosDir = path.join(PLAYER_ROOT, "public", "audios");
  const foundPublic = findFileCached(publicAudiosDir, filename);
  if (foundPublic) return foundPublic;

  if (rawAudiosDir) {
    const foundRaw = findFileCached(rawAudiosDir, filename);
    if (foundRaw) return foundRaw;
  }

  return null;
}

function readJsonFileSafe(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
}

function resolvePartAudioPath(feedback, rawAudiosDir) {
  const audioId = String(feedback.audioId || "");
  const subtitleSourcePath = String(feedback.subtitleSourcePath || "");
  if (!audioId.startsWith("part_") && !subtitleSourcePath.includes(`${path.sep}03_parts${path.sep}`)) {
    return null;
  }
  if (!subtitleSourcePath || !fs.existsSync(subtitleSourcePath) || !rawAudiosDir || !fs.existsSync(rawAudiosDir)) {
    return null;
  }

  const partDoc = readJsonFileSafe(subtitleSourcePath);
  const meta = partDoc?.meta && typeof partDoc.meta === "object" ? partDoc.meta : partDoc;
  const rawSourceFile = typeof meta?.source_file === "string" ? meta.source_file.trim() : "";

  const partsRoot = process.env.PARTS_ROOT_DIR || path.join(DATA_ROOT, "03_parts");
  const relativeSourcePath = path.relative(partsRoot, subtitleSourcePath);
  const yearBucket =
    relativeSourcePath && !relativeSourcePath.startsWith("..") && !path.isAbsolute(relativeSourcePath)
      ? relativeSourcePath.split(path.sep)[0]
      : "";

  const candidates = [];
  const pushCandidate = (candidate) => {
    if (!candidate) return;
    const resolved = path.resolve(candidate);
    if (!candidates.includes(resolved)) {
      candidates.push(resolved);
    }
  };

  if (rawSourceFile) {
    const sourceMp3 = rawSourceFile.replace(/\.json$/i, ".mp3");
    if (yearBucket) {
      pushCandidate(path.join(rawAudiosDir, yearBucket, sourceMp3));
    }
    pushCandidate(path.join(rawAudiosDir, sourceMp3));
    pushCandidate(findFileCached(rawAudiosDir, path.basename(sourceMp3)));
  }

  const partDirBase = path.basename(path.dirname(subtitleSourcePath)).replace(/_processed$/i, "");
  if (partDirBase) {
    const partDirMp3 = `${partDirBase}.mp3`;
    if (yearBucket) {
      pushCandidate(path.join(rawAudiosDir, yearBucket, partDirMp3));
    }
    pushCandidate(findFileCached(rawAudiosDir, partDirMp3));
  }

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return null;
}

function extractFeedbackHint(message) {
  if (!message) return null;
  const normalized = String(message).trim();
  if (!normalized) return null;

  const recognizedAsMatch = normalized.match(/^(.+?)(?:这?两个字)?识别成了(.+?)[。！？!?.，,]*$/);
  if (recognizedAsMatch) {
    return {
      original: recognizedAsMatch[2].trim(),
      replacement: recognizedAsMatch[1].replace(/这?两个字$/, "").trim(),
      source: "recognized_as",
    };
  }

  const arrowMatch = normalized.match(/(.+?)[-—>→]{1,2}\s*(.+)/);
  if (arrowMatch) {
    return {
      original: arrowMatch[1].trim(),
      replacement: arrowMatch[2].trim(),
      source: "arrow",
    };
  }

  const shouldBeMatch = normalized.match(/(.+?)应为[“"']?(.+?)[”"']?$/);
  if (shouldBeMatch) {
    return {
      original: shouldBeMatch[1].trim(),
      replacement: shouldBeMatch[2].trim(),
      source: "should_be",
    };
  }

  const parts = normalized.split(/\s+/).filter(Boolean);
  if (parts.length === 2 && parts[0] !== parts[1]) {
    return {
      original: parts[0],
      replacement: parts[1],
      source: "whitespace_pair",
    };
  }

  return null;
}

function tryApplyExplicitFeedbackHint(input) {
  const hint = input.feedbackHint;
  const currentText = input?.target?.currentText;
  if (!hint || !hint.original || !hint.replacement || !currentText) {
    return null;
  }

  if (!currentText.includes(hint.original)) {
    return null;
  }

  const correctedText = currentText.replace(hint.original, hint.replacement);
  if (correctedText === currentText) {
    return null;
  }

  return {
    decision: "APPLY",
    confidence: 0.995,
    operation: "REPLACE_CURRENT",
    correctedText,
    summary: `用户反馈明确指出“${hint.original}”应为“${hint.replacement}”，已按最小替换直接修复。`,
    updatedPrevText: null,
    updatedNextText: null,
    source: "explicit_feedback_hint",
  };
}

function parseJsonFromText(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    throw new Error("empty output");
  }

  const directCandidates = [text];
  const fencedMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fencedMatch?.[1]) {
    directCandidates.push(fencedMatch[1].trim());
  }
  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    directCandidates.push(text.slice(firstBrace, lastBrace + 1));
  }

  for (const candidate of directCandidates) {
    try {
      return JSON.parse(candidate);
    } catch {}
  }

  throw new Error(`unable to parse JSON from output: ${text.slice(0, 300)}`);
}

function extractAudioClip(audioPath, startSeconds, endSeconds, outputPath) {
  const clipStart = Math.max(0, startSeconds - AUDIO_CLIP_PAD_SECONDS);
  const clipEnd = Math.max(clipStart + 0.5, endSeconds + AUDIO_CLIP_PAD_SECONDS);
  const duration = Math.max(0.5, clipEnd - clipStart);
  const ffmpegBin = process.env.FFMPEG_BIN || "ffmpeg";
  const result = spawnSync(
    ffmpegBin,
    [
      "-y",
      "-ss",
      String(clipStart),
      "-t",
      String(duration),
      "-i",
      audioPath,
      "-ac",
      "1",
      "-ar",
      "16000",
      "-vn",
      outputPath,
    ],
    {
      cwd: ROOT,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    }
  );

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`ffmpeg 切片失败: exit=${result.status} stderr=${result.stderr || ""}`);
  }

  return {
    clipPath: outputPath,
    clipStart,
    clipEnd,
    duration,
  };
}

function chooseAudioClipWindow(feedback, audioPath) {
  const looksLikeClipAudio =
    audioPath.includes(`${path.sep}public${path.sep}audios${path.sep}single${path.sep}`) ||
    audioPath.includes(`${path.sep}public${path.sep}audios${path.sep}conversations${path.sep}`);

  const relativeStart = typeof feedback.subtitleStart === "number" ? feedback.subtitleStart : null;
  const relativeEnd = typeof feedback.subtitleEnd === "number" ? feedback.subtitleEnd : null;
  const absoluteStart =
    typeof feedback.subtitleAbsStart === "number" ? feedback.subtitleAbsStart : null;
  const absoluteEnd = typeof feedback.subtitleAbsEnd === "number" ? feedback.subtitleAbsEnd : null;

  if (looksLikeClipAudio && relativeStart != null && relativeEnd != null) {
    return {
      startSeconds: relativeStart,
      endSeconds: relativeEnd,
      basis: "relative_clip_time",
    };
  }

  if (absoluteStart != null && absoluteEnd != null) {
    return {
      startSeconds: absoluteStart,
      endSeconds: absoluteEnd,
      basis: "absolute_source_time",
    };
  }

  if (relativeStart != null && relativeEnd != null) {
    return {
      startSeconds: relativeStart,
      endSeconds: relativeEnd,
      basis: "relative_fallback",
    };
  }

  return null;
}

async function transcribeAudioClip(clipPath, input) {
  if (!BIGMODEL_API_KEY) {
    return {
      enabled: false,
      reason: "FEEDBACK_REPAIR_BIGMODEL_API_KEY missing",
    };
  }

  const fileBuffer = fs.readFileSync(clipPath);
  const form = new FormData();
  form.append("model", TRANSCRIBE_MODEL);
  form.append("stream", "false");
  form.append(
    "prompt",
    [
      "音频语言是中文。",
      "请尽量忠实转写，不要概括。",
      `疑似待确认字幕：${input.target.currentText}`,
      input.feedbackHint?.replacement
        ? `用户提示可能应改为：${input.feedbackHint.replacement}`
        : "",
    ]
      .filter(Boolean)
      .join("\n")
  );
  const hotwords = [...new Set([input.feedbackHint?.original, input.feedbackHint?.replacement].filter(Boolean))];
  for (const hotword of hotwords) {
    form.append("hotwords[]", hotword);
  }
  form.append("file", new Blob([fileBuffer], { type: "audio/wav" }), path.basename(clipPath));

  const response = await fetch(`${BIGMODEL_BASE_URL}/audio/transcriptions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${BIGMODEL_API_KEY}`,
    },
    body: form,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      sanitizeErrorMessage(`BigModel transcription failed: ${response.status} ${text}`)
    );
  }

  const data = await response.json();
  const transcriptText =
    typeof data?.text === "string"
      ? data.text.trim()
      : typeof data === "string"
        ? data.trim()
        : "";

  return {
    enabled: true,
    model: TRANSCRIBE_MODEL,
    text: transcriptText,
    raw: data,
  };
}

function buildPrompt(input) {
  return `你是一个字幕纠错代理。
你的任务是根据用户反馈、目标字幕和上下文，判断这条字幕是否需要修复。

规则：
1. 只修正明显的 ASR 识别错误、错别字、同音误识别。
2. 不要润色，不要改写风格，不要扩写。
3. 优先最小编辑。
4. 如果用户反馈里明确给出了替换词、纠正词、对照词，必须优先遵循该反馈，不要擅自改成别的词。
5. 如果有音频转写证据，优先结合音频转写判断；音频证据优先级高于纯上下文推断。
6. 只有当“用户反馈 + 音频证据 + 上下文”共同支持时，才允许做超出用户原话的推断。
7. 如果无法从用户反馈明确判断，而音频证据也不足，要更保守，宁可返回 NEEDS_HUMAN。
8. 仅当你非常确定时才返回 APPLY。
9. 如果 feedbackHint 明确给出 original/replacement，应优先使用该映射。
10. 如果用户明确指出“当前字幕开头的一小段其实属于上一句”，且音频/上下文支持，可以使用 operation=MOVE_PREFIX_TO_PREV。
11. 如果用户明确指出“当前字幕结尾的一小段其实属于下一句”，且音频/上下文支持，可以使用 operation=MOVE_SUFFIX_TO_NEXT。
12. operation=REPLACE_CURRENT 时，只改当前句：correctedText=修正后的当前句，updatedPrevText=null，updatedNextText=null。
13. operation=MOVE_PREFIX_TO_PREV 时：correctedText=移除前缀后的当前句；updatedPrevText=把该前缀并回上一句后的上一句；updatedNextText=null。
14. operation=MOVE_SUFFIX_TO_NEXT 时：correctedText=移除后缀后的当前句；updatedNextText=把该后缀并回下一句后的下一句；updatedPrevText=null。
15. 只有在相邻句真实存在、且你能给出最小编辑结果时，才允许跨句移动；否则返回 NEEDS_HUMAN。
16. 尽量保持原字幕风格；如果原字幕基本不加标点，就不要凭空补很多标点。
17. 输出必须严格符合 JSON Schema，不能输出任何额外文字。

以下是任务输入 JSON：
${JSON.stringify(input, null, 2)}
`;
}

function loadSourceTarget(feedback) {
  const sourcePath = feedback.subtitleSourcePath;
  const sourceKind = feedback.subtitleSourceKind;
  const sourceIndex = feedback.subtitleSourceIndex;

  if (!sourcePath || !sourceKind || typeof sourceIndex !== "number") {
    throw new Error("Feedback 缺少原始字幕定位信息，无法自动修复");
  }
  const safeSourcePath = assertSafeSubtitleSourcePath(sourcePath);
  if (!fs.existsSync(safeSourcePath)) {
    throw new Error(`原始字幕文件不存在: ${safeSourcePath}`);
  }

  const content = JSON.parse(fs.readFileSync(safeSourcePath, "utf-8"));
  const collectionKey = sourceKind === "sentences" ? "sentences" : "segments";
  const items = Array.isArray(content[collectionKey]) ? content[collectionKey] : null;
  if (!items) {
    throw new Error(`原始字幕文件缺少数组字段: ${collectionKey}`);
  }

  const target = items[sourceIndex];
  if (!target || typeof target.text !== "string") {
    throw new Error(`无法定位原始字幕 index=${sourceIndex}`);
  }
  const prevItem = sourceIndex > 0 ? items[sourceIndex - 1] : null;
  const nextItem = sourceIndex + 1 < items.length ? items[sourceIndex + 1] : null;

  const getText = (item) => (item && typeof item.text === "string" ? item.text : null);
  const prev = items.slice(Math.max(0, sourceIndex - 2), sourceIndex).map(getText).filter(Boolean);
  const next = items.slice(sourceIndex + 1, sourceIndex + 3).map(getText).filter(Boolean);

  return {
    content,
    safeSourcePath,
    collectionKey,
    items,
    target,
    prevItem,
    nextItem,
    prev,
    next,
  };
}

async function backfillMissingJobs() {
  const feedbacks = await prisma.feedback.findMany({
    where: {
      repairStatus: "pending",
      subtitleSourcePath: { not: null },
      subtitleSourceKind: { not: null },
      subtitleSourceIndex: { not: null },
      repairJobs: { none: {} },
    },
    select: { id: true },
    take: 20,
  });

  for (const feedback of feedbacks) {
    await prisma.feedbackRepairJob.create({
      data: {
        feedbackId: feedback.id,
        status: "pending",
        promptVersion: PROMPT_VERSION,
      },
    });
  }
}

async function claimNextJob() {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const job = await prisma.feedbackRepairJob.findFirst({
      where: { status: "pending" },
      orderBy: { createdAt: "asc" },
    });

    if (!job) {
      return null;
    }

    const claimed = await prisma.$transaction(async (tx) => {
      const now = new Date();
      const updated = await tx.feedbackRepairJob.updateMany({
        where: {
          id: job.id,
          status: "pending",
        },
        data: {
          status: "running",
          attempt: job.attempt + 1,
          startedAt: now,
          finishedAt: null,
          error: null,
        },
      });

      if (updated.count !== 1) {
        return null;
      }

      await tx.feedback.update({
        where: { id: job.feedbackId },
        data: {
          processingStatus: "处理中",
          repairStatus: "running",
          repairError: null,
        },
      });

      return tx.feedbackRepairJob.findUnique({
        where: { id: job.id },
      });
    });

    if (claimed) {
      return claimed;
    }
  }

  return null;
}

function buildInput(feedback, targetInfo) {
  const feedbackHint = extractFeedbackHint(feedback.message);
  return {
    feedback: {
      id: feedback.id,
      message: feedback.message,
      createdAt: feedback.createdAt.toISOString(),
    },
    feedbackHint:
      feedbackHint && targetInfo.target.text.includes(feedbackHint.original)
        ? feedbackHint
        : null,
    audio: {
      id: feedback.audioId,
      filename: feedback.audioFilename,
      date: feedback.audioDate,
      personTag: feedback.audioPersonTag,
      clipStartTime: feedback.audioStartTime,
      clipEndTime: feedback.audioEndTime,
    },
    target: {
      sourceKind: feedback.subtitleSourceKind,
      sourcePath: targetInfo.safeSourcePath,
      sourceIndex: feedback.subtitleSourceIndex,
      currentText: targetInfo.target.text,
      displayText: feedback.subtitleText,
      absStart: feedback.subtitleAbsStart ?? targetInfo.target.start ?? null,
      absEnd: feedback.subtitleAbsEnd ?? targetInfo.target.end ?? null,
    },
    context: {
      prev: targetInfo.prev,
      next: targetInfo.next,
      immediatePrev: targetInfo.prevItem
        ? {
            text: targetInfo.prevItem.text,
            start: targetInfo.prevItem.start ?? null,
            end: targetInfo.prevItem.end ?? null,
          }
        : null,
      immediateNext: targetInfo.nextItem
        ? {
            text: targetInfo.nextItem.text,
            start: targetInfo.nextItem.start ?? null,
            end: targetInfo.nextItem.end ?? null,
          }
        : null,
    },
    policy: {
      minimalEditOnly: true,
      allowRewriteWholeSentence: false,
      autoApplyConfidenceThreshold: AUTO_APPLY_CONFIDENCE,
    },
  };
}

function runCodexTask(taskDir, prompt) {
  const outputPath = path.join(taskDir, "output.json");
  const args = ["-a", "never", "-s", "read-only", "-C", taskDir];
  if (MODEL) {
    args.push("-m", MODEL);
  }
  if (USE_OSS) {
    args.push("--oss");
    if (LOCAL_PROVIDER) {
      args.push("--local-provider", LOCAL_PROVIDER);
    }
  }
  args.push(
    "exec",
    "--ephemeral",
    "--skip-git-repo-check",
    "--output-schema",
    OUTPUT_SCHEMA_PATH,
    "-o",
    outputPath,
    "-"
  );

  const childEnv = { ...process.env };
  delete childEnv.OPENAI_API_KEY;
  delete childEnv.OPENAI_BASE_URL;

  const result = spawnSync(CODEX_BIN, args, {
    cwd: ROOT,
    input: prompt,
    encoding: "utf-8",
    maxBuffer: 10 * 1024 * 1024,
    env: childEnv,
  });

  fs.writeFileSync(path.join(taskDir, "codex.stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "codex.stderr.log"), result.stderr || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stderr.log"), result.stderr || "", "utf-8");

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`codex exec 失败: exit=${result.status}`);
  }
  if (!fs.existsSync(outputPath)) {
    throw new Error("codex exec 未生成 output.json");
  }

  return JSON.parse(fs.readFileSync(outputPath, "utf-8"));
}

function runTraeTask(taskDir, prompt) {
  const result = spawnSync("traecli", ["--yolo", "--print", prompt], {
    cwd: ROOT,
    encoding: "utf-8",
    maxBuffer: 10 * 1024 * 1024,
    env: process.env,
  });

  fs.writeFileSync(path.join(taskDir, "traecli.stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "traecli.stderr.log"), result.stderr || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stderr.log"), result.stderr || "", "utf-8");

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`traecli failed: exit=${result.status}`);
  }

  return parseJsonFromText(result.stdout || "");
}

function runAidenTask(taskDir, prompt) {
  const result = spawnSync(
    "aiden",
    ["--permission-mode", "agentFull", "--one-shot", "--print", prompt],
    {
      cwd: ROOT,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
      env: process.env,
    }
  );

  fs.writeFileSync(path.join(taskDir, "aiden.stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "aiden.stderr.log"), result.stderr || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stdout.log"), result.stdout || "", "utf-8");
  fs.writeFileSync(path.join(taskDir, "stderr.log"), result.stderr || "", "utf-8");

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`aiden failed: exit=${result.status}`);
  }

  return parseJsonFromText(result.stdout || "");
}

function runJudgeTask(taskDir, prompt) {
  const backends = (process.env.FEEDBACK_REPAIR_JUDGE_BACKENDS || "codex,traecli,aiden")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  const errors = [];
  for (const backend of backends) {
    try {
      if (backend === "codex") {
        return { backend, output: runCodexTask(taskDir, prompt) };
      }
      if (backend === "traecli") {
        return { backend, output: runTraeTask(taskDir, prompt) };
      }
      if (backend === "aiden") {
        return { backend, output: runAidenTask(taskDir, prompt) };
      }
      errors.push(`${backend}: unsupported backend`);
    } catch (error) {
      errors.push(`${backend}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throw new Error(`all judge backends failed: ${errors.join(" | ")}`);
}

function normalizeOutputText(value) {
  return typeof value === "string" ? value.trim() : null;
}

function normalizeRepairOutput(output) {
  const decision = String(output?.decision || "").toUpperCase();
  const confidence = typeof output?.confidence === "number" ? output.confidence : null;
  const summary = typeof output?.summary === "string" ? output.summary.trim() : "";
  const correctedText = normalizeOutputText(output?.correctedText);
  const updatedPrevText = normalizeOutputText(output?.updatedPrevText);
  const updatedNextText = normalizeOutputText(output?.updatedNextText);
  let operation =
    typeof output?.operation === "string" && output.operation.trim()
      ? output.operation.trim().toUpperCase()
      : null;

  if (decision === "APPLY" && !operation) {
    if (updatedPrevText && !updatedNextText) {
      operation = "MOVE_PREFIX_TO_PREV";
    } else if (updatedNextText && !updatedPrevText) {
      operation = "MOVE_SUFFIX_TO_NEXT";
    } else {
      operation = "REPLACE_CURRENT";
    }
  }

  return {
    decision,
    confidence,
    summary,
    operation,
    correctedText,
    updatedPrevText,
    updatedNextText,
  };
}

function buildRepairPatch(input, repair) {
  const operation = repair.operation || "REPLACE_CURRENT";
  const changes = [];

  if (
    repair.correctedText != null &&
    repair.correctedText !== input.target.currentText
  ) {
    changes.push({
      role: "current",
      sourceIndex: input.target.sourceIndex,
      before: input.target.currentText,
      after: repair.correctedText,
    });
  }

  if (
    repair.updatedPrevText != null &&
    repair.updatedPrevText !== input.context.immediatePrev?.text
  ) {
    changes.push({
      role: "prev",
      sourceIndex:
        typeof input.target.sourceIndex === "number" ? input.target.sourceIndex - 1 : null,
      before: input.context.immediatePrev?.text ?? null,
      after: repair.updatedPrevText,
    });
  }

  if (
    repair.updatedNextText != null &&
    repair.updatedNextText !== input.context.immediateNext?.text
  ) {
    changes.push({
      role: "next",
      sourceIndex:
        typeof input.target.sourceIndex === "number" ? input.target.sourceIndex + 1 : null,
      before: input.context.immediateNext?.text ?? null,
      after: repair.updatedNextText,
    });
  }

  if (changes.length === 0) {
    return null;
  }

  return {
    operation,
    sourceKind: input.target.sourceKind,
    sourcePath: input.target.sourcePath,
    changes,
  };
}

async function markJobAndFeedback(jobId, feedbackId, updates) {
  const now = new Date();
  await prisma.$transaction(async (tx) => {
    await tx.feedbackRepairJob.update({
      where: { id: jobId },
      data: {
        status: updates.jobStatus,
        model:
          updates.model ||
          MODEL ||
          (USE_OSS ? `oss:${LOCAL_PROVIDER || "default"}` : "codex"),
        promptVersion: PROMPT_VERSION,
        inputJson: updates.inputJson,
        outputJson: updates.outputJson,
        patchJson: updates.patchJson ?? null,
        error: updates.error || null,
        finishedAt: now,
      },
    });

    await tx.feedback.update({
      where: { id: feedbackId },
      data: {
        repairStatus: updates.feedbackStatus,
        processingStatus: updates.processingStatus ?? "已处理",
        repairSummary: updates.repairSummary ?? null,
        repairConfidence:
          typeof updates.repairConfidence === "number" ? updates.repairConfidence : null,
        repairedText: updates.repairedText ?? null,
        repairPatchJson: updates.repairPatchJson ?? null,
        repairError: updates.repairError ?? null,
        processedAt: updates.processingStatus === "处理中" ? null : now,
        repairedAt: updates.feedbackStatus === "applied" ? now : null,
      },
    });
  });
}

function applyPatch(feedback, repair, expectedTexts) {
  const sourcePath = assertSafeSubtitleSourcePath(feedback.subtitleSourcePath);
  const sourceKind = feedback.subtitleSourceKind;
  const sourceIndex = feedback.subtitleSourceIndex;
  const doc = JSON.parse(fs.readFileSync(sourcePath, "utf-8"));
  const collectionKey = sourceKind === "sentences" ? "sentences" : "segments";
  const items = doc[collectionKey];
  const target = items?.[sourceIndex];
  const prev = sourceIndex > 0 ? items?.[sourceIndex - 1] : null;
  const next = sourceIndex + 1 < items?.length ? items?.[sourceIndex + 1] : null;

  if (!target || typeof target.text !== "string") {
    throw new Error("回写前再次定位原始字幕失败");
  }

  const operation = repair.operation || "REPLACE_CURRENT";
  const correctedText = repair.correctedText;
  const updatedPrevText = repair.updatedPrevText;
  const updatedNextText = repair.updatedNextText;

  if (operation === "MOVE_PREFIX_TO_PREV") {
    if (!prev || typeof prev.text !== "string") {
      throw new Error("上一句不存在，无法执行 MOVE_PREFIX_TO_PREV");
    }
    if (!correctedText || !updatedPrevText) {
      throw new Error("MOVE_PREFIX_TO_PREV 缺少 correctedText 或 updatedPrevText");
    }
    if (target.text === correctedText && prev.text === updatedPrevText) {
      return { alreadyApplied: true };
    }
    if (target.text !== expectedTexts.current || prev.text !== expectedTexts.prev) {
      throw new Error("原始字幕内容已变化，跨句回写已中止，请人工确认");
    }
    prev.text = updatedPrevText;
    target.text = correctedText;
    atomicWriteJson(sourcePath, doc);
    return { alreadyApplied: false };
  }

  if (operation === "MOVE_SUFFIX_TO_NEXT") {
    if (!next || typeof next.text !== "string") {
      throw new Error("下一句不存在，无法执行 MOVE_SUFFIX_TO_NEXT");
    }
    if (!correctedText || !updatedNextText) {
      throw new Error("MOVE_SUFFIX_TO_NEXT 缺少 correctedText 或 updatedNextText");
    }
    if (target.text === correctedText && next.text === updatedNextText) {
      return { alreadyApplied: true };
    }
    if (target.text !== expectedTexts.current || next.text !== expectedTexts.next) {
      throw new Error("原始字幕内容已变化，跨句回写已中止，请人工确认");
    }
    target.text = correctedText;
    next.text = updatedNextText;
    atomicWriteJson(sourcePath, doc);
    return { alreadyApplied: false };
  }

  if (!correctedText) {
    throw new Error("REPLACE_CURRENT 缺少 correctedText");
  }
  if (target.text === correctedText) {
    return { alreadyApplied: true };
  }
  if (target.text !== expectedTexts.current) {
    throw new Error("原始字幕内容已变化，自动回写已中止，请人工确认");
  }
  target.text = correctedText;
  atomicWriteJson(sourcePath, doc);
  return { alreadyApplied: false };
}

async function processJob(job) {
  const fullJob = await prisma.feedbackRepairJob.findUnique({
    where: { id: job.id },
    include: { feedback: true },
  });

  if (!fullJob || !fullJob.feedback) {
    throw new Error(`Job 或 Feedback 不存在: ${job.id}`);
  }

  const feedback = fullJob.feedback;
  const targetInfo = loadSourceTarget(feedback);
  const input = buildInput(feedback, targetInfo);
  const taskDir = path.join(WORKDIR, job.id);
  ensureDir(taskDir);

  const audioPath = resolveAudioPath(feedback);
  const clipWindow = audioPath ? chooseAudioClipWindow(feedback, audioPath) : null;
  if (audioPath && clipWindow) {
    let clipInfo = null;
    try {
      clipInfo = extractAudioClip(
        audioPath,
        clipWindow.startSeconds,
        clipWindow.endSeconds,
        path.join(taskDir, "clip.wav")
      );
      input.audioEvidence = {
        audioPath,
        clipBasis: clipWindow.basis,
        ...clipInfo,
      };
      const transcript = await transcribeAudioClip(clipInfo.clipPath, input);
      input.audioEvidence.transcription = transcript;
    } catch (error) {
      input.audioEvidence = {
        audioPath,
        clipBasis: clipWindow.basis,
        ...(clipInfo || {}),
        error: sanitizeErrorMessage(error instanceof Error ? error.message : String(error)),
      };
    }
  } else {
    input.audioEvidence = {
      error: audioPath ? "缺少可用的时间范围，无法切片" : "无法定位音频文件",
    };
  }

  fs.writeFileSync(path.join(taskDir, "input.json"), `${JSON.stringify(input, null, 2)}\n`, "utf-8");
  let output;
  let judgeBackend = "rule";
  const explicitDecision = tryApplyExplicitFeedbackHint(input);
  if (explicitDecision) {
    judgeBackend = "rule:explicit_feedback_hint";
    output = explicitDecision;
    fs.writeFileSync(
      path.join(taskDir, "prompt.txt"),
      "explicit feedback hint matched; codex skipped\n",
      "utf-8"
    );
  } else {
    const prompt = buildPrompt(input);
    fs.writeFileSync(path.join(taskDir, "prompt.txt"), prompt, "utf-8");
    const judged = runJudgeTask(taskDir, prompt);
    judgeBackend = judged.backend;
    output = judged.output;
  }
  const normalized = normalizeRepairOutput(output);
  const decision = normalized.decision;
  const confidence = normalized.confidence;
  const correctedText = normalized.correctedText;
  const updatedPrevText = normalized.updatedPrevText;
  const updatedNextText = normalized.updatedNextText;
  const operation = normalized.operation;
  const outputJson = JSON.stringify(output, null, 2);
  const inputJson = JSON.stringify(input, null, 2);
  const summary = normalized.summary;
  const repairPatch = buildRepairPatch(input, normalized);
  const repairPatchJson = repairPatch ? JSON.stringify(repairPatch, null, 2) : null;
  const hasPatch =
    (correctedText != null && correctedText !== input.target.currentText) ||
    (updatedPrevText != null && updatedPrevText !== input.context.immediatePrev?.text) ||
    (updatedNextText != null && updatedNextText !== input.context.immediateNext?.text);

  if (decision === "APPLY" && hasPatch) {
    if (confidence != null && confidence < AUTO_APPLY_CONFIDENCE) {
      await markJobAndFeedback(job.id, feedback.id, {
        jobStatus: "needs_human",
        feedbackStatus: "needs_human",
        repairSummary: `${summary}（置信度不足，未自动应用）`,
        repairConfidence: confidence,
        repairedText: correctedText,
        repairPatchJson,
        patchJson: repairPatchJson,
        model: judgeBackend,
        inputJson,
        outputJson,
      });
      return;
    }

    const patchResult = applyPatch(
      feedback,
      {
        operation,
        correctedText,
        updatedPrevText,
        updatedNextText,
      },
      {
        current: input.target.currentText,
        prev: input.context.immediatePrev?.text ?? null,
        next: input.context.immediateNext?.text ?? null,
      }
    );
    await markJobAndFeedback(job.id, feedback.id, {
      jobStatus: "applied",
      feedbackStatus: "applied",
      repairSummary: patchResult.alreadyApplied ? `${summary}（原文件已是修复结果）` : summary,
      repairConfidence: confidence,
      repairedText: correctedText,
      repairPatchJson,
      patchJson: repairPatchJson,
      model: judgeBackend,
      inputJson,
      outputJson,
    });
    return;
  }

  if (decision === "REJECT") {
    await markJobAndFeedback(job.id, feedback.id, {
      jobStatus: "rejected",
      feedbackStatus: "rejected",
      repairSummary: summary || "AI 判断原字幕无需修复",
      repairConfidence: confidence,
      repairedText: correctedText,
      repairPatchJson,
      patchJson: repairPatchJson,
      model: judgeBackend,
      inputJson,
      outputJson,
    });
    return;
  }

  await markJobAndFeedback(job.id, feedback.id, {
    jobStatus: "needs_human",
    feedbackStatus: "needs_human",
    repairSummary: summary || "AI 无法高置信判断，需人工处理",
    repairConfidence: confidence,
    repairedText: correctedText,
    repairPatchJson,
    patchJson: repairPatchJson,
    model: judgeBackend,
    inputJson,
    outputJson,
  });
}

async function failJob(job, error) {
  const message = error instanceof Error ? error.message : String(error);
  await markJobAndFeedback(job.id, job.feedbackId, {
    jobStatus: "failed",
    feedbackStatus: "failed",
    repairSummary: null,
    repairConfidence: null,
    repairedText: null,
    repairPatchJson: null,
    patchJson: null,
    repairError: message,
    error: message,
  });
}

async function tick() {
  await backfillMissingJobs();
  const job = await claimNextJob();
  if (!job) {
    return false;
  }

  try {
    await processJob(job);
  } catch (error) {
    await failJob(job, error);
  }
  return true;
}

async function main() {
  if (!ENABLED) {
    console.log("feedback worker disabled by FEEDBACK_REPAIR_ENABLED=false");
    return;
  }

  ensureDir(WORKDIR);
  console.log(`feedback worker started, workdir=${WORKDIR}`);

  do {
    const handled = await tick();
    if (RUN_ONCE) {
      break;
    }
    if (!handled) {
      await sleep(POLL_MS);
    }
  } while (!stopped);
}

process.on("SIGINT", () => {
  stopped = true;
});
process.on("SIGTERM", () => {
  stopped = true;
});

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
