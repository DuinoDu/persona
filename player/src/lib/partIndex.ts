import crypto from "crypto";
import fs from "fs";
import path from "path";

export interface PartRecord {
  id: string;
  date: string;
  dateLabel: string;
  yearBucket: string;
  title: string;
  personTag: string;
  kind: string;
  startSec: number;
  endSec: number;
  startTime: string;
  endTime: string;
  partJsonPath: string;
  partRelativePath: string;
  sourceAudioPath: string | null;
  sourceFile: string | null;
  sourceAudioPublicName: string | null;
  displayFilename: string;
  subtitleFile: string;
}

interface PartDateSummary {
  value: string;
  label: string;
  count: number;
}

interface PartIndexData {
  dates: PartDateSummary[];
  partsByDate: Map<string, PartRecord[]>;
  partsById: Map<string, PartRecord>;
}

interface PartMetaDocument {
  meta?: {
    source_file?: string;
    title?: string;
    kind?: string;
    persona?: string;
    start?: number;
    end?: number;
    start_ts?: string;
    end_ts?: string;
  };
}

const CN_DATE_RE = /(\d{4})年(\d{1,2})月(\d{1,2})日/;
const ISO_DATE_RE = /(\d{4})-(\d{1,2})-(\d{1,2})/;
const DATA_ROOT = path.resolve(process.cwd(), "..", "data");
const PARTS_ROOT = process.env.PARTS_ROOT_DIR || path.join(DATA_ROOT, "03_parts");
const RAW_AUDIO_ROOT = process.env.RAW_AUDIOS_DIR || path.join(DATA_ROOT, "01_downloads");

let cachedIndex: PartIndexData | null = null;

function hasJsonExtension(filename: string) {
  return filename.toLowerCase().endsWith(".json");
}

function collectFilesRecursive(dir: string, files: string[] = []) {
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

function sanitizeFilenameSegment(value: string) {
  return value
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function toIsoDate(year: string | number, month: string | number, day: string | number) {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function toCnDateLabel(isoDate: string) {
  const [year, month, day] = isoDate.split("-").map((part) => Number(part));
  return `${year}年${month}月${day}日`;
}

function extractIsoDate(...inputs: Array<string | null | undefined>) {
  for (const rawInput of inputs) {
    const input = rawInput || "";
    const cnMatch = input.match(CN_DATE_RE);
    if (cnMatch) {
      return toIsoDate(cnMatch[1], cnMatch[2], cnMatch[3]);
    }
    const isoMatch = input.match(ISO_DATE_RE);
    if (isoMatch) {
      return toIsoDate(isoMatch[1], isoMatch[2], isoMatch[3]);
    }
    const compactMatch = input.match(/(\d{4})(\d{2})(\d{2})/);
    if (compactMatch) {
      return toIsoDate(compactMatch[1], compactMatch[2], compactMatch[3]);
    }
  }
  return null;
}

function formatDisplayTime(seconds: number) {
  const total = Math.max(0, seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function formatCompactTime(seconds: number) {
  const total = Math.max(0, seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  return `${String(hours).padStart(2, "0")}${String(minutes).padStart(2, "0")}${String(secs).padStart(2, "0")}`;
}

function stripPartPrefix(value: string) {
  return value
    .replace(/^\d+[_-]?/, "")
    .replace(/_final$/i, "")
    .replace(/_(连麦|評論|评论|开场|结束语|結束語|返场|返場)$/u, "")
    .trim();
}

function normalizeKind(metaKind: string | null | undefined, filename: string) {
  const kind = (metaKind || "").toLowerCase();
  if (kind) return kind;
  if (filename.includes("开场")) return "opening";
  if (filename.includes("结束")) return "ending";
  if (filename.includes("评论") || filename.includes("評論")) return "comment";
  if (filename.includes("连麦") || filename.includes("連麥")) return "call";
  return "part";
}

function normalizePersonTag(doc: PartMetaDocument, filename: string) {
  const persona = (doc.meta?.persona || "").trim();
  if (persona) return persona;
  const title = (doc.meta?.title || "").trim();
  if (title) {
    const stripped = stripPartPrefix(title);
    if (stripped) return stripped;
  }
  const basename = path.basename(filename, ".json");
  return stripPartPrefix(basename) || basename;
}

function buildDisplayFilename(dateLabel: string, startSec: number, endSec: number, personTag: string, id: string) {
  const safeTag = sanitizeFilenameSegment(personTag || "part") || "part";
  return `${dateLabel}_${formatCompactTime(startSec)}_${formatCompactTime(endSec)}_${safeTag}_${id.slice(0, 8)}.mp3`;
}

function buildPartId(relativePath: string) {
  return `part_${crypto.createHash("sha1").update(relativePath).digest("hex").slice(0, 16)}`;
}

function buildRawAudioMap() {
  const exactByRelativeBase = new Map<string, string>();
  const exactByBaseName = new Map<string, string>();
  const byDate = new Map<string, string[]>();

  if (!fs.existsSync(RAW_AUDIO_ROOT)) {
    return { exactByRelativeBase, exactByBaseName, byDate };
  }

  for (const filePath of collectFilesRecursive(RAW_AUDIO_ROOT)) {
    if (!filePath.toLowerCase().endsWith(".mp3")) continue;
    const relative = path.relative(RAW_AUDIO_ROOT, filePath);
    const relativeBase = relative.replace(/\.mp3$/i, "");
    exactByRelativeBase.set(relativeBase, filePath);
    exactByBaseName.set(path.basename(relativeBase), filePath);

    const isoDate = extractIsoDate(path.basename(filePath), relative);
    if (isoDate) {
      const list = byDate.get(isoDate) ?? [];
      list.push(filePath);
      byDate.set(isoDate, list);
    }
  }

  return { exactByRelativeBase, exactByBaseName, byDate };
}

function resolveSourceAudioPath(params: {
  yearBucket: string;
  partDirRelative: string;
  sourceFile: string | null;
  isoDate: string;
  rawAudioMap: ReturnType<typeof buildRawAudioMap>;
}) {
  const { yearBucket, partDirRelative, sourceFile, isoDate, rawAudioMap } = params;
  if (sourceFile) {
    const exactRelative = path.join(yearBucket, sourceFile.replace(/\.json$/i, ""));
    const exact = rawAudioMap.exactByRelativeBase.get(exactRelative);
    if (exact) return exact;
    const base = path.basename(sourceFile, ".json");
    const byBase = rawAudioMap.exactByBaseName.get(base);
    if (byBase) return byBase;
  }

  const dirBase = path.basename(partDirRelative.replace(/_processed$/i, ""));
  const exactFromDir = rawAudioMap.exactByRelativeBase.get(path.join(yearBucket, dirBase));
  if (exactFromDir) return exactFromDir;
  const byDirBase = rawAudioMap.exactByBaseName.get(dirBase);
  if (byDirBase) return byDirBase;

  const matchesByDate = rawAudioMap.byDate.get(isoDate) ?? [];
  if (matchesByDate.length === 1) {
    return matchesByDate[0];
  }
  if (matchesByDate.length > 1) {
    const matchingYear = matchesByDate.find((candidate) => candidate.includes(`${path.sep}${yearBucket}${path.sep}`));
    if (matchingYear) return matchingYear;
    return matchesByDate[0];
  }

  return null;
}

function buildIndex(): PartIndexData {
  const partsByDate = new Map<string, PartRecord[]>();
  const partsById = new Map<string, PartRecord>();
  const dates: PartDateSummary[] = [];

  if (!fs.existsSync(PARTS_ROOT)) {
    return { dates, partsByDate, partsById };
  }

  const rawAudioMap = buildRawAudioMap();
  const allFiles = collectFilesRecursive(PARTS_ROOT).filter((filePath) => hasJsonExtension(filePath));

  for (const filePath of allFiles) {
    const relativePath = path.relative(PARTS_ROOT, filePath);
    if (relativePath.endsWith("formal_output.schema.json")) continue;

    let doc: PartMetaDocument;
    try {
      doc = JSON.parse(fs.readFileSync(filePath, "utf-8")) as PartMetaDocument;
    } catch {
      continue;
    }

    const sourceFile = doc.meta?.source_file ?? null;
    const isoDate = extractIsoDate(sourceFile, relativePath, path.dirname(relativePath));
    if (!isoDate) continue;

    const yearBucket = relativePath.split(path.sep)[0] || "unknown";
    const partDirRelative = path.dirname(relativePath);
    const startSec = typeof doc.meta?.start === "number" ? doc.meta.start : 0;
    const endSec = typeof doc.meta?.end === "number" ? doc.meta.end : startSec;
    const id = buildPartId(relativePath);
    const dateLabel = toCnDateLabel(isoDate);
    const personTag = normalizePersonTag(doc, filePath);
    const title = (doc.meta?.title || path.basename(filePath, ".json")).trim();
    const sourceAudioPath = resolveSourceAudioPath({
      yearBucket,
      partDirRelative,
      sourceFile,
      isoDate,
      rawAudioMap,
    });

    const record: PartRecord = {
      id,
      date: isoDate,
      dateLabel,
      yearBucket,
      title,
      personTag,
      kind: normalizeKind(doc.meta?.kind, path.basename(filePath)),
      startSec,
      endSec,
      startTime: doc.meta?.start_ts || formatDisplayTime(startSec),
      endTime: doc.meta?.end_ts || formatDisplayTime(endSec),
      partJsonPath: filePath,
      partRelativePath: relativePath,
      sourceAudioPath,
      sourceFile,
      sourceAudioPublicName: sourceAudioPath ? path.basename(sourceAudioPath) : null,
      displayFilename: buildDisplayFilename(dateLabel, startSec, endSec, personTag, id),
      subtitleFile: path.basename(filePath),
    };

    const list = partsByDate.get(isoDate) ?? [];
    list.push(record);
    partsByDate.set(isoDate, list);
    partsById.set(id, record);
  }

  for (const [value, items] of partsByDate.entries()) {
    items.sort((a, b) => a.startSec - b.startSec || a.endSec - b.endSec || a.title.localeCompare(b.title, "zh-CN"));
    dates.push({
      value,
      label: toCnDateLabel(value),
      count: items.length,
    });
  }

  dates.sort((a, b) => b.value.localeCompare(a.value));

  return { dates, partsByDate, partsById };
}

function getIndex() {
  if (!cachedIndex) {
    cachedIndex = buildIndex();
  }
  return cachedIndex;
}

export function hasPartDataset() {
  return getIndex().dates.length > 0;
}

export function listAvailableDates() {
  return getIndex().dates;
}

export function listPartsByDate(date: string) {
  return getIndex().partsByDate.get(date) ?? [];
}

export function getPartById(id: string) {
  return getIndex().partsById.get(id) ?? null;
}

export function resetPartIndexCache() {
  cachedIndex = null;
}
