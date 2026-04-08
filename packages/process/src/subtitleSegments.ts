import fs from "fs";
import path from "path";
import { loadSingleManifest } from "./singleManifest";
import { getPartById } from "./partIndex";
import { getDefaultRawTextsRoot } from "./runtimePaths";

interface Segment {
  start: number;
  end: number;
  speaker: string;
  text: string;
  role?: string;
}

interface IndexedSegment extends Segment {
  sourceIndex: number;
}

interface IndexedSentence {
  speaker_id?: string;
  speaker_name?: string;
  start: number;
  end: number;
  text: string;
  sourceIndex: number;
}

export interface DisplaySegment {
  start: number;
  end: number;
  text: string;
  role: string;
  sourceKind: "sentences" | "segments";
  sourcePath: string;
  sourceIndex: number;
  absStart: number;
  absEnd: number;
}

interface RawJsonV1 {
  start_time: number;
  end_time?: number;
  source_file?: string;
  host_speaker?: string;
  guest_speaker?: string;
  segments: Segment[];
}

interface RawJsonV2 {
  meta?: {
    start_time?: number;
    end_time?: number;
    source_file?: string;
    host_speaker_label?: string;
    guest_speaker_labels?: string[];
  };
  segments: Segment[];
}

type RawJson = RawJsonV1 | RawJsonV2;

interface FileIndex {
  files: string[];
  byName: Map<string, string[]>;
  bySuffixCache: Map<string, string | null>;
}

const fileIndexCache = new Map<string, FileIndex>();
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

function getFileIndex(dir: string): FileIndex | null {
  const resolvedDir = path.resolve(dir);
  if (!fs.existsSync(resolvedDir)) {
    return null;
  }

  const cached = fileIndexCache.get(resolvedDir);
  if (cached) {
    return cached;
  }

  const files = collectFilesRecursive(resolvedDir);
  const byName = new Map<string, string[]>();
  for (const filePath of files) {
    const filename = path.basename(filePath);
    const list = byName.get(filename) ?? [];
    list.push(filePath);
    byName.set(filename, list);
  }

  const index: FileIndex = {
    files,
    byName,
    bySuffixCache: new Map(),
  };
  fileIndexCache.set(resolvedDir, index);
  return index;
}

function findFileRecursiveCached(dir: string, filename: string): string | null {
  const index = getFileIndex(dir);
  if (!index) return null;
  return index.byName.get(filename)?.[0] ?? null;
}

function findFileBySuffixRecursiveCached(dir: string, suffix: string): string | null {
  const index = getFileIndex(dir);
  if (!index) return null;
  if (index.bySuffixCache.has(suffix)) {
    return index.bySuffixCache.get(suffix) ?? null;
  }

  const found = index.files.find((filePath) => path.basename(filePath).endsWith(suffix)) ?? null;
  index.bySuffixCache.set(suffix, found);
  return found;
}

function resolveTranscriptsDir(rawTextsDir: string): string {
  if (process.env.RAW_TRANSCRIPTS_DIR) {
    return process.env.RAW_TRANSCRIPTS_DIR;
  }

  const normalized = path.resolve(rawTextsDir);
  return normalized.replace(
    `${path.sep}04_conversations_v2${path.sep}`,
    `${path.sep}03_transcripts${path.sep}`
  );
}

function toRole(
  speaker: string,
  hostSpeaker?: string,
  guestSpeakers: string[] = []
) {
  if (!speaker.startsWith("SPEAKER_")) {
    return speaker;
  }
  if (hostSpeaker && speaker === hostSpeaker) {
    return "host";
  }
  if (guestSpeakers.includes(speaker)) {
    return "guest";
  }
  return speaker === "SPEAKER_01" ? "guest" : "host";
}

function withSegmentIndexes(segments: Segment[]): IndexedSegment[] {
  return segments.map((segment, index) => ({
    ...segment,
    sourceIndex: index,
  }));
}

function normalizeSegments(
  segments: IndexedSegment[],
  clipStartTime: number,
  hostSpeaker: string | undefined,
  guestSpeakers: string[],
  sourcePath: string
): DisplaySegment[] {
  return segments
    .filter((s) => s.text && s.text.trim())
    .map((s) => ({
      start: s.start - clipStartTime,
      end: s.end - clipStartTime,
      text: s.text,
      role: toRole(s.speaker, hostSpeaker, guestSpeakers),
      sourceKind: "segments" as const,
      sourcePath,
      sourceIndex: s.sourceIndex,
      absStart: s.start,
      absEnd: s.end,
    }));
}

function normalizeSentences(
  sentences: IndexedSentence[],
  clipStartTime: number,
  sourcePath: string
): DisplaySegment[] {
  return sentences
    .filter((s) => s.text && s.text.trim())
    .map((s) => ({
      start: s.start - clipStartTime,
      end: s.end - clipStartTime,
      text: s.text,
      role:
        s.speaker_id === "host"
          ? "host"
          : s.speaker_id === "guest"
            ? "guest"
            : s.speaker_name || s.speaker_id || "UNKNOWN",
      sourceKind: "sentences" as const,
      sourcePath,
      sourceIndex: s.sourceIndex,
      absStart: s.start,
      absEnd: s.end,
    }));
}

function guessHostSpeaker(segments: Segment[]) {
  const greetingKeywords = ["哈喽", "你好", "来下一个", "下一位", "拜拜", "欢迎", "谢谢"];
  const greetingScores = new Map<string, number>();
  const durationScores = new Map<string, number>();

  for (const seg of segments) {
    const speaker = seg.speaker || "UNKNOWN";
    const text = seg.text || "";
    let greetingScore = greetingScores.get(speaker) ?? 0;
    for (const kw of greetingKeywords) {
      if (text.includes(kw)) {
        greetingScore += 1;
      }
    }
    greetingScores.set(speaker, greetingScore);
    durationScores.set(
      speaker,
      (durationScores.get(speaker) ?? 0) + Math.max(0, seg.end - seg.start)
    );
  }

  const bestGreeting = [...greetingScores.entries()].sort((a, b) => b[1] - a[1])[0];
  if (bestGreeting && bestGreeting[1] > 0) {
    return bestGreeting[0];
  }

  const bestDuration = [...durationScores.entries()].sort((a, b) => b[1] - a[1])[0];
  return bestDuration?.[0];
}

function getSubtitleMeta(jsonContent: RawJson) {
  if ("start_time" in jsonContent) {
    return {
      startTime: jsonContent.start_time,
      endTime: jsonContent.end_time,
      sourceFile: jsonContent.source_file,
      hostSpeaker: jsonContent.host_speaker,
      guestSpeakers: jsonContent.guest_speaker ? [jsonContent.guest_speaker] : [],
    };
  }

  return {
    startTime: jsonContent.meta?.start_time ?? 0,
    endTime: jsonContent.meta?.end_time,
    sourceFile: jsonContent.meta?.source_file,
    hostSpeaker: jsonContent.meta?.host_speaker_label,
    guestSpeakers: jsonContent.meta?.guest_speaker_labels ?? [],
  };
}

function normalizeTranscriptDocument(
  transcriptPath: string,
  transcriptContent: unknown
): DisplaySegment[] | null {
  if (!transcriptContent || typeof transcriptContent !== "object") {
    return null;
  }

  const doc = transcriptContent as {
    meta?: { start?: number };
    sentences?: Array<{
      speaker_id?: string;
      speaker_name?: string;
      start: number;
      end: number;
      text: string;
    }>;
    segments?: Segment[];
    start_time?: number;
    host_speaker?: string;
    guest_speaker?: string;
  };

  if (Array.isArray(doc.sentences) && doc.sentences.length > 0) {
    const clipStartTime = doc.meta?.start ?? 0;
    return normalizeSentences(
      doc.sentences.map((sentence, index) => ({
        ...sentence,
        sourceIndex: index,
      })),
      clipStartTime,
      transcriptPath
    );
  }

  if (Array.isArray(doc.segments) && doc.segments.length > 0) {
    const transcriptHostSpeaker = guessHostSpeaker(doc.segments);
    const transcriptGuestSpeakers = [...new Set(doc.segments.map((s) => s.speaker))].filter(
      (speaker) => speaker && speaker !== transcriptHostSpeaker
    );
    return normalizeSegments(
      withSegmentIndexes(doc.segments),
      doc.start_time ?? 0,
      doc.host_speaker ?? transcriptHostSpeaker,
      doc.guest_speaker ? [doc.guest_speaker] : transcriptGuestSpeakers,
      transcriptPath
    );
  }

  return null;
}

export function resolveSubtitleSegmentsForAudio(decodedFilename: string): DisplaySegment[] {
  const manifestItems = loadSingleManifest();
  if (manifestItems) {
    const manifestItem = manifestItems.find((item) => item.filename === decodedFilename);
    if (manifestItem?.subtitleJsonPath && fs.existsSync(manifestItem.subtitleJsonPath)) {
      const subtitleContent = JSON.parse(
        fs.readFileSync(manifestItem.subtitleJsonPath, "utf-8")
      ) as {
        meta?: { start?: number };
        sentences?: Array<{
          speaker_id?: string;
          speaker_name?: string;
          start: number;
          end: number;
          text: string;
        }>;
      };

      const clipStartTime = subtitleContent.meta?.start ?? 0;
      const normalizedSentences = normalizeSentences(
        (subtitleContent.sentences ?? []).map((sentence, index) => ({
          ...sentence,
          sourceIndex: index,
        })),
        clipStartTime,
        manifestItem.subtitleJsonPath
      );
      return normalizedSentences;
    }
  }

  const singleAudioFilename = process.env.SINGLE_AUDIO_FILENAME;
  const singleTranscriptFile = process.env.SINGLE_TRANSCRIPT_FILE;
  if (
    singleAudioFilename &&
    singleTranscriptFile &&
    decodedFilename === singleAudioFilename &&
    fs.existsSync(singleTranscriptFile)
  ) {
    const transcriptContent = JSON.parse(
      fs.readFileSync(singleTranscriptFile, "utf-8")
    ) as { segments?: Segment[] };
    const transcriptSegments = (transcriptContent.segments ?? []).filter(
      (s) => s.text && s.text.trim()
    );
    const hostSpeaker = guessHostSpeaker(transcriptSegments);
    const guestSpeakers = [...new Set(transcriptSegments.map((s) => s.speaker))].filter(
      (speaker) => speaker && speaker !== hostSpeaker
    );

    const normalizedSegments = normalizeSegments(
      withSegmentIndexes(transcriptContent.segments ?? []),
      0,
      hostSpeaker,
      guestSpeakers,
      singleTranscriptFile
    );
    return normalizedSegments;
  }

  const jsonFilename = decodedFilename.replace(/\.mp3$/i, ".json");
  const rawTextsDir = process.env.RAW_TEXTS_DIR || getDefaultRawTextsRoot();
  const transcriptsDir = resolveTranscriptsDir(rawTextsDir);

  const directTranscriptPath = fs.existsSync(transcriptsDir)
    ? findFileRecursiveCached(transcriptsDir, jsonFilename)
    : null;
  if (directTranscriptPath && fs.existsSync(directTranscriptPath)) {
    const directTranscriptContent = JSON.parse(
      fs.readFileSync(directTranscriptPath, "utf-8")
    );
    const normalizedDirectTranscript = normalizeTranscriptDocument(
      directTranscriptPath,
      directTranscriptContent
    );
    if (normalizedDirectTranscript && normalizedDirectTranscript.length > 0) {
      return normalizedDirectTranscript;
    }
  }

  const transcriptSuffix = jsonFilename.includes("_")
    ? jsonFilename.slice(jsonFilename.indexOf("_") + 1)
    : jsonFilename;
  const suffixTranscriptPath = !directTranscriptPath && fs.existsSync(transcriptsDir)
    ? findFileBySuffixRecursiveCached(transcriptsDir, transcriptSuffix)
    : null;
  if (suffixTranscriptPath && fs.existsSync(suffixTranscriptPath)) {
    const suffixTranscriptContent = JSON.parse(
      fs.readFileSync(suffixTranscriptPath, "utf-8")
    );
    const normalizedSuffixTranscript = normalizeTranscriptDocument(
      suffixTranscriptPath,
      suffixTranscriptContent
    );
    if (normalizedSuffixTranscript && normalizedSuffixTranscript.length > 0) {
      return normalizedSuffixTranscript;
    }
  }

  let jsonPath = fs.existsSync(rawTextsDir) ? findFileRecursiveCached(rawTextsDir, jsonFilename) : null;

  if (!jsonPath) {
    const suffix = jsonFilename.includes("_")
      ? jsonFilename.slice(jsonFilename.indexOf("_") + 1)
      : jsonFilename;
    jsonPath = fs.existsSync(rawTextsDir)
      ? findFileBySuffixRecursiveCached(rawTextsDir, suffix)
      : null;
  }

  if (!jsonPath || !fs.existsSync(jsonPath)) {
    throw new Error("Subtitle not found");
  }

  const jsonContent = JSON.parse(fs.readFileSync(jsonPath, "utf-8")) as RawJson;
  const { startTime, endTime, sourceFile, hostSpeaker, guestSpeakers } = getSubtitleMeta(jsonContent);

  if (sourceFile && typeof endTime === "number") {
    const transcriptPath = fs.existsSync(transcriptsDir)
      ? findFileRecursiveCached(transcriptsDir, sourceFile)
      : null;

    if (transcriptPath && fs.existsSync(transcriptPath)) {
      const transcriptContent = JSON.parse(
        fs.readFileSync(transcriptPath, "utf-8")
      ) as { segments?: Segment[] };

      const fineSegments = withSegmentIndexes(transcriptContent.segments ?? [])
        .filter((s) => s.text && s.text.trim() && s.end >= startTime && s.start <= endTime)
        .map((s) => ({
          ...s,
          start: Math.max(s.start, startTime),
          end: Math.min(s.end, endTime),
        }));

      const normalizedFineSegments = normalizeSegments(
        fineSegments,
        startTime,
        hostSpeaker,
        guestSpeakers,
        transcriptPath
      );

      if (normalizedFineSegments.length > 0) {
        return normalizedFineSegments;
      }
    }
  }

  const normalizedSegments = normalizeSegments(
    withSegmentIndexes(jsonContent.segments ?? []),
    startTime,
    hostSpeaker,
    guestSpeakers,
    jsonPath
  );
  return normalizedSegments;
}

export function resolveSubtitleSegmentsForPartId(partId: string): DisplaySegment[] {
  const part = getPartById(partId);
  if (!part) {
    throw new Error("Part not found");
  }
  if (!fs.existsSync(part.partJsonPath)) {
    throw new Error("Subtitle not found");
  }

  const content = JSON.parse(fs.readFileSync(part.partJsonPath, "utf-8")) as {
    meta?: { start?: number };
    sentences?: Array<{
      speaker_id?: string;
      speaker_name?: string;
      start: number;
      end: number;
      text: string;
    }>;
    segments?: Segment[];
    start_time?: number;
    host_speaker?: string;
    guest_speaker?: string;
  };

  const normalized = normalizeTranscriptDocument(part.partJsonPath, content);
  if (!normalized || normalized.length === 0) {
    throw new Error("Subtitle not found");
  }
  return normalized;
}

function nearlyEqual(a: number | null, b: number, epsilon = 0.35) {
  return typeof a === "number" && Number.isFinite(a) && Math.abs(a - b) <= epsilon;
}

interface ResolveFeedbackTargetParams {
  audioFilename: string;
  subtitleId?: string | null;
  subtitleIndex?: number | null;
  subtitleText?: string | null;
  subtitleStart?: number | null;
  subtitleEnd?: number | null;
}

export function resolveFeedbackTargetForAudio(params: ResolveFeedbackTargetParams): DisplaySegment {
  const segments = params.subtitleId?.startsWith("part_")
    ? resolveSubtitleSegmentsForPartId(params.subtitleId)
    : resolveSubtitleSegmentsForAudio(params.audioFilename);
  const normalizedText = typeof params.subtitleText === "string" ? params.subtitleText.trim() : "";

  const matchesSubmittedValues = (segment: DisplaySegment) => {
    if (normalizedText && segment.text !== normalizedText) {
      return false;
    }
    if (
      typeof params.subtitleStart === "number" &&
      !nearlyEqual(params.subtitleStart, segment.start)
    ) {
      return false;
    }
    if (typeof params.subtitleEnd === "number" && !nearlyEqual(params.subtitleEnd, segment.end)) {
      return false;
    }
    return true;
  };

  if (
    typeof params.subtitleIndex === "number" &&
    Number.isInteger(params.subtitleIndex) &&
    params.subtitleIndex >= 0 &&
    params.subtitleIndex < segments.length
  ) {
    const indexedSegment = segments[params.subtitleIndex];
    if (matchesSubmittedValues(indexedSegment)) {
      return indexedSegment;
    }
  }

  const fallback = segments.find(matchesSubmittedValues);
  if (fallback) {
    return fallback;
  }

  throw new Error("Unable to resolve subtitle target from trusted server-side data");
}
