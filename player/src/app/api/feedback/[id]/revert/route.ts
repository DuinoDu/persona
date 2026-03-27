import fs from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function jsonNoStore(body: unknown, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
    },
  });
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

  const rawTextsDir =
    process.env.RAW_TEXTS_DIR || path.join(process.cwd(), "public", "audios", "raw_texts");
  addRoot(resolveTranscriptsDir(rawTextsDir));
  addRoot(process.env.RAW_TRANSCRIPTS_DIR);
  addRoot(process.env.PARTS_ROOT_DIR || path.join(process.cwd(), "..", "data", "03_parts"));

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

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const feedback = await prisma.feedback.findUnique({
    where: { id },
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
    return jsonNoStore({ error: "Feedback not found" }, 404);
  }

  if (!feedback.repairPatchJson) {
    return jsonNoStore({ error: "该修复没有可撤销的 patch" }, 400);
  }

  let patch: RepairPatch;
  try {
    patch = JSON.parse(feedback.repairPatchJson) as RepairPatch;
  } catch {
    return jsonNoStore({ error: "修复 patch 已损坏，无法撤销" }, 400);
  }

  const sourcePath = assertSafeSubtitleSourcePath(
    patch.sourcePath || feedback.subtitleSourcePath || ""
  );
  const sourceKind = patch.sourceKind || feedback.subtitleSourceKind;
  const collectionKey = sourceKind === "sentences" ? "sentences" : "segments";
  const changes = Array.isArray(patch.changes) ? patch.changes : [];

  if (changes.length === 0) {
    return jsonNoStore({ error: "修复 patch 不包含可撤销的变更" }, 400);
  }

  if (!fs.existsSync(sourcePath)) {
    return jsonNoStore({ error: "原始字幕文件不存在" }, 404);
  }

  const doc = JSON.parse(fs.readFileSync(sourcePath, "utf-8")) as Record<string, unknown>;
  const items = Array.isArray(doc[collectionKey]) ? (doc[collectionKey] as Array<Record<string, unknown>>) : null;
  if (!items) {
    return jsonNoStore({ error: `字幕文件缺少数组字段: ${collectionKey}` }, 400);
  }

  let alreadyReverted = true;
  for (const change of changes) {
    const sourceIndex = typeof change.sourceIndex === "number" ? change.sourceIndex : null;
    if (sourceIndex == null || sourceIndex < 0 || sourceIndex >= items.length) {
      return jsonNoStore({ error: "patch 中的字幕索引无效，无法撤销" }, 400);
    }
    const item = items[sourceIndex];
    const currentText = typeof item.text === "string" ? item.text : null;
    if (currentText == null) {
      return jsonNoStore({ error: "当前字幕内容缺失，无法撤销" }, 400);
    }
    if (currentText !== change.before) {
      alreadyReverted = false;
      if (currentText !== change.after) {
        return jsonNoStore({ error: "当前字幕内容已变化，无法安全撤销，请人工处理" }, 409);
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
  await prisma.feedback.update({
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

  return jsonNoStore({
    ok: true,
    alreadyReverted,
  });
}
