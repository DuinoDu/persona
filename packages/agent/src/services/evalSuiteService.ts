import { join } from "node:path";
import { readdir, readFile, stat } from "node:fs/promises";
import { remoteCountEvalSuiteCases } from "@ququ/agent/remoteJobs";
import {
  asNumber,
  asString,
  buildHostConfig,
  type AgentDbClient,
  jsonResult,
} from "./shared";

async function countJsonlLines(filePath: string) {
  try {
    const text = await readFile(filePath, "utf-8");
    return text.split(/\r?\n/).filter((line) => line.trim()).length;
  } catch {
    return 0;
  }
}

export async function countLocalEvalSuiteCases(sourcePath: string) {
  try {
    const sourceStat = await stat(sourcePath);
    if (sourceStat.isFile()) {
      return countJsonlLines(sourcePath);
    }
    if (!sourceStat.isDirectory()) {
      return 0;
    }

    for (const dirPath of [join(sourcePath, "cases"), sourcePath]) {
      try {
        const dirStat = await stat(dirPath);
        if (!dirStat.isDirectory()) {
          continue;
        }
        const entries = await readdir(dirPath, { withFileTypes: true });
        const jsonlFiles = entries
          .filter((entry) => entry.isFile() && entry.name.endsWith(".jsonl"))
          .map((entry) => join(dirPath, entry.name))
          .sort((left, right) => left.localeCompare(right));
        if (jsonlFiles.length === 0) {
          continue;
        }
        const counts = await Promise.all(jsonlFiles.map((filePath) => countJsonlLines(filePath)));
        return counts.reduce((sum, count) => sum + count, 0);
      } catch {
        continue;
      }
    }
  } catch {
    return 0;
  }

  return 0;
}

export async function listEvalSuitesService(input: { db: AgentDbClient }) {
  const items = await input.db.evalSuite.findMany({
    orderBy: { createdAt: "desc" },
  });
  return jsonResult({ items });
}

export async function createEvalSuiteService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const slug = asString(body.slug);
  const title = asString(body.title);
  const sourcePath = asString(body.sourcePath);
  const inferHostId = asString(body.inferHostId);

  if (!slug || !title || !sourcePath) {
    return jsonResult({ error: "Missing required fields" }, 400);
  }

  const explicitCaseCount = Number(body.caseCount);
  let caseCount = Number.isFinite(explicitCaseCount) && explicitCaseCount > 0 ? explicitCaseCount : 0;

  if (caseCount <= 0) {
    caseCount = await countLocalEvalSuiteCases(sourcePath);
  }

  if (caseCount <= 0 && inferHostId) {
    const inferHost = await input.db.inferHost.findUnique({
      where: { id: inferHostId },
    });
    if (inferHost) {
      caseCount = await remoteCountEvalSuiteCases({
        host: buildHostConfig(inferHost)!,
        suitePath: sourcePath,
      });
    }
  }

  const suite = await input.db.evalSuite.create({
    data: {
      slug,
      title,
      sourcePath,
      description: asString(body.description) || null,
      caseCount,
      tagsJson: asString(body.tagsJson) || null,
      status: asString(body.status) || "active",
    },
  });

  return jsonResult(suite);
}
