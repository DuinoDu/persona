import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), ".data");
const PROGRESS_FILE = path.join(DATA_DIR, "playback-progress.json");

function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

function loadAll(): Record<string, number> {
  if (!fs.existsSync(PROGRESS_FILE)) {
    return {};
  }

  try {
    const raw = JSON.parse(fs.readFileSync(PROGRESS_FILE, "utf-8")) as Record<string, unknown>;
    const normalized: Record<string, number> = {};
    for (const [key, value] of Object.entries(raw)) {
      if (typeof value === "number" && Number.isFinite(value)) {
        normalized[key] = value;
      }
    }
    return normalized;
  } catch {
    return {};
  }
}

function saveAll(data: Record<string, number>) {
  ensureDataDir();
  fs.writeFileSync(PROGRESS_FILE, JSON.stringify(data, null, 2), "utf-8");
}

export function getPlaybackPosition(audioKey: string) {
  const data = loadAll();
  return data[audioKey] ?? 0;
}

export function getPlaybackPositions(audioKeys: string[]) {
  const data = loadAll();
  const result: Record<string, number> = {};
  for (const audioKey of audioKeys) {
    result[audioKey] = data[audioKey] ?? 0;
  }
  return result;
}

export function setPlaybackPosition(audioKey: string, position: number) {
  const data = loadAll();
  data[audioKey] = Number.isFinite(position) ? Math.max(0, position) : 0;
  saveAll(data);
  return data[audioKey];
}
