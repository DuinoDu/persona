import { NextRequest } from "next/server";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const exportMocks = vi.hoisted(() => ({
  prisma: {
    badCase: {
      findMany: vi.fn(),
    },
    evalRun: {
      findUnique: vi.fn(),
    },
    trainingExport: {
      findMany: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
    trainingExportItem: {
      create: vi.fn(),
    },
    $transaction: vi.fn(async (operations: Array<Promise<unknown>>) => Promise.all(operations)),
  },
  loadGenerationRecordsFromRun: vi.fn(),
  createExportId: vi.fn(),
  materializeExportBundle: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  prisma: exportMocks.prisma,
}));

vi.mock("@ququ/agent/evalArtifacts", () => ({
  loadGenerationRecordsFromRun: exportMocks.loadGenerationRecordsFromRun,
}));

vi.mock("@ququ/agent/personaExport", async () => {
  const actual = await vi.importActual<typeof import("@ququ/agent/personaExport")>("@ququ/agent/personaExport");
  return {
    ...actual,
    createExportId: exportMocks.createExportId,
    materializeExportBundle: exportMocks.materializeExportBundle,
  };
});

let POST: typeof import("../../../src/app/api/evals/exports/route").POST;

beforeAll(async () => {
  ({ POST } = await import("../../../src/app/api/evals/exports/route"));
});

afterEach(() => {
  exportMocks.prisma.badCase.findMany.mockReset();
  exportMocks.prisma.evalRun.findUnique.mockReset();
  exportMocks.prisma.trainingExport.findMany.mockReset();
  exportMocks.prisma.trainingExport.create.mockReset();
  exportMocks.prisma.trainingExport.update.mockReset();
  exportMocks.prisma.trainingExportItem.create.mockReset();
  exportMocks.prisma.$transaction.mockReset();
  exportMocks.loadGenerationRecordsFromRun.mockReset();
  exportMocks.createExportId.mockReset();
  exportMocks.materializeExportBundle.mockReset();
});

function makeRequest(body: Record<string, unknown>) {
  return new NextRequest("http://localhost/api/evals/exports", {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /api/evals/exports", () => {
  it("creates a training export and returns the bundle path", async () => {
    exportMocks.createExportId.mockReturnValue("export_test_001");
    exportMocks.prisma.badCase.findMany.mockResolvedValue([
      {
        id: "bad-case-1",
        sourceType: "offline_case",
        sourceId: "case-1",
        evalRunId: "run-1",
        caseId: "case-1",
        title: "needs cleanup",
        notes: "demo note",
        editedTargetText: null,
        chosenText: "good answer",
        rejectedText: "bad answer",
        failureTagsJson: JSON.stringify(["hallucination"]),
        rubricScoresJson: JSON.stringify({ helpfulness: 2 }),
        inferenceTrace: null,
      },
    ]);
    exportMocks.prisma.evalRun.findUnique.mockResolvedValue({
      id: "run-1",
      outputDir: "/workspace/output/run-1",
      summaryPath: "/workspace/output/run-1/summary.json",
      inferHost: null,
      modelDeployment: null,
      evalSuite: null,
    });
    exportMocks.loadGenerationRecordsFromRun.mockResolvedValue([
      {
        id: "case-1",
        slice: "slice-a",
        tags: [],
        messages: [{ role: "user", content: "hello" }],
        promptTokens: 10,
        generatedTokens: 7,
        latencyMs: 88,
        rawOutputText: "raw answer",
        cleanOutputText: "clean answer",
        outputCharLen: 11,
        blankOutput: false,
        shortOutput: false,
        containsControlTokens: false,
        runtimeSignature: { model: "demo" },
        generation: { temperature: 0.1 },
        tracePath: "/workspace/output/run-1/traces/case-1.json",
      },
    ]);
    exportMocks.prisma.trainingExport.create.mockResolvedValue({
      id: "export_test_001",
      kind: "preference_pair_candidate",
      status: "running",
      title: "Persona export",
      itemCount: 1,
      configJson: JSON.stringify({}),
    });
    exportMocks.prisma.trainingExportItem.create.mockImplementation(async ({ data }) => ({
      id: "item-1",
      ...data,
    }));
    exportMocks.prisma.trainingExport.update.mockResolvedValue({
      id: "export_test_001",
      kind: "preference_pair_candidate",
      status: "succeeded",
      title: "Persona export",
      itemCount: 1,
      outputPath: "/workspace/artifacts/evals/exports/20260407/export_test_001.jsonl",
      items: [{ id: "item-1" }],
    });
    exportMocks.materializeExportBundle.mockResolvedValue({
      outputDir: "/workspace/artifacts/evals/exports/20260407",
      jsonlPath: "/workspace/artifacts/evals/exports/20260407/export_test_001.jsonl",
      manifestPath: "/workspace/artifacts/evals/exports/20260407/manifest.json",
      readmePath: "/workspace/artifacts/evals/exports/20260407/README.md",
      manifest: {
        export_id: "export_test_001",
        record_count: 1,
        record_types: ["preference_pair_candidate"],
      },
    });

    const response = await POST(
      makeRequest({
        badCaseIds: ["bad-case-1"],
        title: "Persona export",
      })
    );

    expect(response.status).toBe(200);
    expect(exportMocks.prisma.trainingExport.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          id: "export_test_001",
          kind: "preference_pair_candidate",
          status: "running",
          title: "Persona export",
          itemCount: 1,
        }),
      })
    );
    expect(exportMocks.materializeExportBundle).toHaveBeenCalledWith(
      expect.objectContaining({
        exportId: "export_test_001",
        title: "Persona export",
        recordTypes: ["preference_pair_candidate"],
      })
    );
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        jsonlPath: "/workspace/artifacts/evals/exports/20260407/export_test_001.jsonl",
        outputDir: "/workspace/artifacts/evals/exports/20260407",
        export: expect.objectContaining({
          id: "export_test_001",
          status: "succeeded",
        }),
      })
    );
  });
});
