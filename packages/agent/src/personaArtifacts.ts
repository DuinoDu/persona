function sanitizeArtifactToken(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9_-]+/g, "_");
  return normalized.replace(/^_+|_+$/g, "") || "default";
}

function sanitizeArtifactName(value: string) {
  const normalized = value.replace(/[^a-zA-Z0-9._-]+/g, "_");
  return normalized.replace(/^_+|_+$/g, "") || "item";
}

export function buildOfflineEvalTraceDir(workspacePath: string, runId: string) {
  return `${workspacePath}/artifacts/evals/runs/${runId}/traces`;
}

export function buildOfflineEvalTracePath(workspacePath: string, runId: string, caseId: string) {
  return `${buildOfflineEvalTraceDir(workspacePath, runId)}/${sanitizeArtifactName(caseId)}.json`;
}

export function buildLiveServiceTraceDir(workspacePath: string, slug: string) {
  return `${workspacePath}/runtime_logs/live/${sanitizeArtifactToken(slug)}/traces`;
}

export function buildLiveServiceTracePath(
  workspacePath: string,
  slug: string,
  requestId: string
) {
  return `${buildLiveServiceTraceDir(workspacePath, slug)}/${sanitizeArtifactName(requestId)}.json`;
}
