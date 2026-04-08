import { NextRequest } from "next/server";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const ingestMocks = vi.hoisted(() => ({
  prisma: {
    evalRun: {
      findUnique: vi.fn(),
    },
    inferenceTrace: {
      findMany: vi.fn(),
      update: vi.fn(),
      create: vi.fn(),
    },
  },
  loadBatchTraceFromRun: vi.fn(),
  loadGenerationRecordsFromRun: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  prisma: ingestMocks.prisma,
}));

vi.mock("@ququ/agent/evalArtifacts", () => ({
  loadBatchTraceFromRun: ingestMocks.loadBatchTraceFromRun,
  loadGenerationRecordsFromRun: ingestMocks.loadGenerationRecordsFromRun,
}));

let POST: typeof import("../../../src/app/api/evals/runs/[id]/ingest-traces/route").POST;

beforeAll(async () => {
  ({ POST } = await import("../../../src/app/api/evals/runs/[id]/ingest-traces/route"));
});

afterEach(() => {
  ingestMocks.prisma.evalRun.findUnique.mockReset();
  ingestMocks.prisma.inferenceTrace.findMany.mockReset();
  ingestMocks.prisma.inferenceTrace.update.mockReset();
  ingestMocks.prisma.inferenceTrace.create.mockReset();
  ingestMocks.loadBatchTraceFromRun.mockReset();
  ingestMocks.loadGenerationRecordsFromRun.mockReset();
});

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest("http://localhost/api/evals/runs/run-1/ingest-traces", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /api/evals/runs/[id]/ingest-traces", () => {
  it("updates an existing offline trace when force=true", async () => {
    ingestMocks.prisma.evalRun.findUnique.mockResolvedValue({
      id: "run-1",
      outputDir: "/workspace/output/run-1",
      summaryPath: "/workspace/output/run-1/summary.json",
      logPath: "/workspace/output/run-1/run.log",
      status: "succeeded",
      inferHostId: "host-1",
      modelDeploymentId: "deployment-1",
      inferHost: {
        sshHost: "infer.example.com",
        sshPort: 22,
        sshUser: "runner",
        workspacePath: "/workspace",
      },
      modelDeployment: {
        promptVersionId: "prompt-1",
        generationConfigProfileId: "gen-1",
        contextBuilderProfileId: "ctx-1",
      },
      evalSuite: null,
    });
    ingestMocks.loadGenerationRecordsFromRun.mockResolvedValue([
      {
        id: "case-1",
        slice: "slice-a",
        tags: [],
        messages: [{ role: "user", content: "hello" }],
        promptTokens: 12,
        generatedTokens: 8,
        latencyMs: 99,
        rawOutputText: "raw answer",
        cleanOutputText: "clean answer",
        outputCharLen: 12,
        blankOutput: false,
        shortOutput: false,
        containsControlTokens: false,
        runtimeSignature: { model: "demo" },
        generation: { temperature: 0.2 },
        tracePath: "/workspace/output/run-1/traces/case-1.json",
      },
    ]);
    ingestMocks.prisma.inferenceTrace.findMany.mockResolvedValue([
      { id: "trace-1", caseId: "case-1" },
    ]);
    ingestMocks.loadBatchTraceFromRun.mockResolvedValue({
      runtime_signature: { model: "demo" },
      request: {
        messages: [{ role: "user", content: "hello" }],
        generation: { temperature: 0.2 },
        trace_meta: { source: "offline" },
      },
      response: {
        clean_output_text: "clean answer",
        raw_output_text: "raw answer",
      },
      metrics: {
        prompt_tokens: 15,
        generated_tokens: 9,
        latency_ms: 100,
      },
      artifacts: {
        trace_path: "/workspace/output/run-1/traces/case-1.json",
      },
    });
    ingestMocks.prisma.inferenceTrace.update.mockResolvedValue({ id: "trace-1" });

    const response = await POST(makeRequest({ force: true }), {
      params: Promise.resolve({ id: "run-1" }),
    });

    expect(response.status).toBe(200);
    expect(ingestMocks.prisma.inferenceTrace.update).toHaveBeenCalledTimes(1);
    expect(ingestMocks.prisma.inferenceTrace.create).not.toHaveBeenCalled();
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        runId: "run-1",
        totalCases: 1,
        imported: 0,
        updated: 1,
        skipped: 0,
        missingTraceArtifacts: 0,
        force: true,
      })
    );
  });
});
