import fs from "fs";

export interface SingleManifestItem {
  id: string;
  filename: string;
  filepath: string;
  date: string;
  startTime: string;
  endTime: string;
  personTag: string;
  lastPosition: number;
  subtitleJsonPath?: string;
}

let manifestCache:
  | {
      file: string;
      mtimeMs: number;
      items: SingleManifestItem[] | null;
    }
  | null = null;

export function loadSingleManifest(): SingleManifestItem[] | null {
  const manifestFile = process.env.SINGLE_MANIFEST_FILE;
  if (!manifestFile || !fs.existsSync(manifestFile)) {
    manifestCache = null;
    return null;
  }

  const stat = fs.statSync(manifestFile);
  if (
    manifestCache &&
    manifestCache.file === manifestFile &&
    manifestCache.mtimeMs === stat.mtimeMs
  ) {
    return manifestCache.items;
  }

  const content = JSON.parse(fs.readFileSync(manifestFile, "utf-8"));
  const items = Array.isArray(content) ? content : content.items;
  const normalized = Array.isArray(items) ? items : null;
  manifestCache = {
    file: manifestFile,
    mtimeMs: stat.mtimeMs,
    items: normalized,
  };
  return normalized;
}

export function isSingleMode() {
  return Boolean(loadSingleManifest() || process.env.SINGLE_AUDIO_FILENAME);
}
