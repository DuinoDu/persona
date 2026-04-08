import {
  loadBatchTraceFromRun,
  parseBatchTraceViewerId,
} from "@ququ/agent/evalArtifacts";
import {
  buildHostConfig,
  type AgentDbClient,
  jsonResult,
} from "./shared";

export async function getEvalTraceService(input: {
  db: AgentDbClient;
  traceViewerId: string;
}) {
  const parsed = parseBatchTraceViewerId(input.traceViewerId);
  if (!parsed) {
    return jsonResult({ error: "Invalid trace id" }, 400);
  }

  const run = await input.db.evalRun.findUnique({
    where: { id: parsed.runId },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    return jsonResult({ error: "Run not found" }, 404);
  }

  const trace = await loadBatchTraceFromRun(
    {
      outputDir: run.outputDir,
      inferHost: buildHostConfig(run.inferHost),
    },
    parsed.caseId
  );

  if (!trace) {
    return jsonResult(
      {
        error: "Trace not found",
        runId: run.id,
        caseId: parsed.caseId,
      },
      404
    );
  }

  return jsonResult({
    run: {
      id: run.id,
      title: run.title,
      status: run.status,
      mode: run.mode,
      kind: run.kind,
      outputDir: run.outputDir,
      summaryPath: run.summaryPath,
      inferHost: run.inferHost
        ? {
            name: run.inferHost.name,
            sshHost: run.inferHost.sshHost,
            sshPort: run.inferHost.sshPort,
            sshUser: run.inferHost.sshUser,
            workspacePath: run.inferHost.workspacePath,
          }
        : null,
      modelDeployment: run.modelDeployment
        ? {
            id: run.modelDeployment.id,
            name: run.modelDeployment.name,
            slug: run.modelDeployment.slug,
          }
        : null,
      evalSuite: run.evalSuite
        ? {
            id: run.evalSuite.id,
            title: run.evalSuite.title,
            slug: run.evalSuite.slug,
          }
        : null,
    },
    trace,
  });
}
