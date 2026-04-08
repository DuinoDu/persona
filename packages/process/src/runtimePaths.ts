import fs from "node:fs";
import path from "node:path";

let cachedRepoRoot: string | null | undefined;
let cachedPlayerRoot: string | undefined;

function findAncestorDir(startDir: string, predicate: (dir: string) => boolean) {
  let current = path.resolve(startDir);
  while (true) {
    if (predicate(current)) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function isRepoRoot(dir: string) {
  return (
    fs.existsSync(path.join(dir, "data")) &&
    fs.existsSync(path.join(dir, "packages", "player", "package.json")) &&
    fs.existsSync(path.join(dir, "packages", "process", "package.json"))
  );
}

function isPlayerRoot(dir: string) {
  return (
    fs.existsSync(path.join(dir, "package.json")) &&
    fs.existsSync(path.join(dir, "next.config.ts")) &&
    fs.existsSync(path.join(dir, "src", "app", "page.tsx"))
  );
}

export function getRepoRoot(): string | null {
  if (cachedRepoRoot !== undefined) {
    return cachedRepoRoot;
  }

  const explicitRoot = process.env.QUQU_REPO_ROOT?.trim();
  if (explicitRoot) {
    cachedRepoRoot = path.resolve(explicitRoot);
    return cachedRepoRoot;
  }

  cachedRepoRoot = findAncestorDir(process.cwd(), isRepoRoot);
  return cachedRepoRoot;
}

export function getPlayerRoot(): string {
  if (cachedPlayerRoot !== undefined) {
    return cachedPlayerRoot;
  }

  const explicitRoot = process.env.QUQU_PLAYER_ROOT?.trim();
  if (explicitRoot) {
    cachedPlayerRoot = path.resolve(explicitRoot);
    return cachedPlayerRoot;
  }

  const repoRoot = getRepoRoot();
  if (repoRoot) {
    cachedPlayerRoot = path.join(repoRoot, "packages", "player");
    return cachedPlayerRoot;
  }

  cachedPlayerRoot = findAncestorDir(process.cwd(), isPlayerRoot) || process.cwd();
  return cachedPlayerRoot;
}

export function getPlayerPublicRoot() {
  return path.join(getPlayerRoot(), "public");
}

export function getPlayerAudiosRoot() {
  return path.join(getPlayerPublicRoot(), "audios");
}

export function getPlayerStateDir() {
  return path.join(getPlayerRoot(), ".data");
}

export function getDataRoot() {
  const explicitRoot =
    process.env.QUQU_DATA_ROOT?.trim() ||
    process.env.DATA_ROOT_DIR?.trim();
  if (explicitRoot) {
    return path.resolve(explicitRoot);
  }

  const repoRoot = getRepoRoot();
  if (repoRoot) {
    return path.join(repoRoot, "data");
  }

  return path.resolve(getPlayerRoot(), "..", "..", "data");
}

export function getDefaultPartsRoot() {
  return path.join(getDataRoot(), "03_parts");
}

export function getDefaultRawAudioRoot() {
  return path.join(getDataRoot(), "01_downloads");
}

export function getDefaultRawTextsRoot() {
  return path.join(getPlayerAudiosRoot(), "raw_texts");
}
