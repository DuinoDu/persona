import { readFile } from "node:fs/promises";
import type { GenerationRecord } from "@ququ/agent/evalArtifacts";
import { loadGenerationRecordsFromRun } from "@ququ/agent/evalArtifacts";
import {
  buildPreferencePairRecord,
  buildSftCandidateRecord,
  createExportId,
  materializeExportBundle,
  type PersonaExportMode,
  type PersonaExportOverride,
  type PersonaExportSourceType,
  normalizeExportMode,
  resolveExportRecordType,
  resolveFailureTags,
  resolveRubricScores,
  resolveTraceSnapshot,
} from "@ququ/agent/personaExport";
import {
  asOptionalString,
  asRecord,
  asString,
  asStringArray,
  parseJsonMaybe,
  type AgentDbClient,
  jsonResult,
  uniqueStrings,
} from "./shared";

async function loadBadCasesByIds(db: AgentDbClient, ids: string[]) {
  return db.badCase.findMany({
    where: { id: { in: ids } },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalRun: { include: { inferHost: true, modelDeployment: true, evalSuite: true } },
      liveSession: {
        include: { inferHost: true, modelDeployment: true, turns: { orderBy: { createdAt: "asc" } } },
      },
      liveTurn: true,
      inferenceTrace: {
        include: {
          inferHost: true,
          modelDeployment: true,
          evalRun: { include: { inferHost: true, modelDeployment: true, evalSuite: true } },
          liveSession: { include: { inferHost: true, modelDeployment: true } },
          liveTurn: true,
          promptVersion: true,
          generationConfigProfile: true,
          contextBuilderProfile: true,
        },
      },
    },
  });
}

async function loadGenerationRecordMap(db: AgentDbClient, badCases: Record<string, unknown>[]) {
  const evalRunIds = uniqueStrings(
    badCases.map((item) => asOptionalString(item.evalRunId))
  );
  const entries = await Promise.all(
    evalRunIds.map(async (runId) => {
      const run = await db.evalRun.findUnique({
        where: { id: runId },
        include: { inferHost: true, modelDeployment: true, evalSuite: true },
      });
      if (!run) return [runId, [] as GenerationRecord[]] as const;
      const records = await loadGenerationRecordsFromRun(run);
      return [runId, records] as const;
    })
  );
  return new Map(entries);
}

function getOverride(overrides: Record<string, PersonaExportOverride> | null, badCaseId: string) {
  return overrides?.[badCaseId] || null;
}

export async function listTrainingExportsService(input: { db: AgentDbClient }) {
  const items = await input.db.trainingExport.findMany({
    orderBy: { createdAt: "desc" },
    take: 50,
    include: {
      items: { orderBy: { createdAt: "asc" } },
    },
  });

  return jsonResult({
    items: items.map((item: Record<string, unknown>) => ({
      ...item,
      configJson: parseJsonMaybe(item.configJson as string | null | undefined),
      summaryJson: parseJsonMaybe(item.summaryJson as string | null | undefined),
    })),
  });
}

export async function createTrainingExportService(input: {
  db: AgentDbClient;
  body?: Record<string, unknown> | null;
}) {
  const body = input.body ?? {};
  const badCaseIds = asStringArray(body.badCaseIds);
  const mode = normalizeExportMode(body.recordKind);
  const title = asOptionalString(body.title) || `Persona export @ ${new Date().toISOString()}`;
  const annotatorId = asOptionalString(body.annotatorId);
  const reviewerId = asOptionalString(body.reviewerId);
  const notes = asOptionalString(body.notes);
  const overrideMap = asRecord(body.overridesByBadCaseId) as Record<string, PersonaExportOverride> | null;

  if (badCaseIds.length === 0) {
    return jsonResult({ error: "badCaseIds is required" }, 400);
  }

  const badCases = (await loadBadCasesByIds(input.db, badCaseIds)) as Record<string, unknown>[];
  if (badCases.length === 0) {
    return jsonResult({ error: "No bad cases found" }, 404);
  }

  const generationRecordMap = await loadGenerationRecordMap(input.db, badCases);
  const exportId = createExportId();
  const records: unknown[] = [];
  const itemMeta: Array<{ badCaseId: string; sourceType: string; sourceId: string | null }> = [];
  const recordTypes = new Set<string>();
  const skipped: Array<{ badCaseId: string; reason: string }> = [];

  for (const badCase of badCases) {
    const badCaseId = String(badCase.id);
    const override = getOverride(overrideMap, badCaseId);
    const trace = badCase.inferenceTrace ? (badCase.inferenceTrace as Record<string, unknown>) : null;
    const generationRecord =
      asOptionalString(badCase.evalRunId) && asOptionalString(badCase.caseId)
        ? generationRecordMap
            .get(asOptionalString(badCase.evalRunId) || "")
            ?.find((item) => item.id === badCase.caseId) || null
        : null;
    const snapshot = resolveTraceSnapshot(badCase, trace, generationRecord);
    const selectedType = resolveExportRecordType(mode as PersonaExportMode, badCase, override);

    if (!selectedType) {
      skipped.push({ badCaseId, reason: "missing editedTargetText or chosen/rejected text" });
      continue;
    }

    const failureTags = resolveFailureTags(badCase);
    const rubricScores = resolveRubricScores(badCase);
    const sourcePath =
      override?.sourcePath ||
      snapshot.sourcePath ||
      asOptionalString(trace?.remoteArtifactPath) ||
      null;
    const tracePath = override?.tracePath || asOptionalString(trace?.remoteArtifactPath) || null;
    const sourceType = asString(badCase.sourceType) || "offline_case";

    if (selectedType === "sft_candidate") {
      const editedTargetText =
        asOptionalString(override?.editedTargetText) || asOptionalString(badCase.editedTargetText) || "";
      const modelOutput =
        asOptionalString(override?.modelOutput) ||
        snapshot.modelOutput ||
        asOptionalString(generationRecord?.cleanOutputText) ||
        asOptionalString(generationRecord?.rawOutputText) ||
        "";
      if (!editedTargetText || !modelOutput) {
        skipped.push({ badCaseId, reason: "missing editedTargetText or model_output" });
        continue;
      }
      const record = buildSftCandidateRecord({
        badCase: {
          ...badCase,
          failureTagsJson: JSON.stringify(failureTags),
          rubricScoresJson: JSON.stringify(rubricScores),
          sourcePath,
        },
        sourceType: sourceType as PersonaExportSourceType,
        inputMessages: override?.inputMessages || snapshot.inputMessages,
        modelOutput,
        editedTargetText,
        runtimeSignature: snapshot.runtimeSignature,
        generationConfig: snapshot.generationConfig,
        trace,
        tracePath,
        sourcePath,
        annotatorId,
        reviewerId,
      });
      records.push(record);
      const recordSource = asRecord((record as Record<string, unknown>).source);
      itemMeta.push({ badCaseId, sourceType, sourceId: asOptionalString(recordSource?.source_id) });
      recordTypes.add("sft_candidate");
      continue;
    }

    const chosenText = asOptionalString(override?.chosenText) || asOptionalString(badCase.chosenText) || "";
    const rejectedText =
      asOptionalString(override?.rejectedText) || asOptionalString(badCase.rejectedText) || "";
    if (!chosenText || !rejectedText) {
      skipped.push({ badCaseId, reason: "missing chosenText or rejectedText" });
      continue;
    }
    const record = buildPreferencePairRecord({
      badCase: {
        ...badCase,
        failureTagsJson: JSON.stringify(failureTags),
        rubricScoresJson: JSON.stringify(rubricScores),
        sourcePath,
      },
      sourceType: sourceType as PersonaExportSourceType,
      contextMessages: override?.inputMessages || snapshot.inputMessages,
      chosenText,
      rejectedText,
      runtimeSignature: snapshot.runtimeSignature,
      generationConfig: snapshot.generationConfig,
      trace,
      tracePath,
      sourcePath,
      annotatorId,
      reviewerId,
    });
    records.push(record);
    const recordSource = asRecord((record as Record<string, unknown>).source);
    itemMeta.push({ badCaseId, sourceType, sourceId: asOptionalString(recordSource?.source_id) });
    recordTypes.add("preference_pair_candidate");
  }

  if (records.length === 0) {
    return jsonResult({ error: "No exportable records", skipped }, 400);
  }

  const effectiveRecordTypes = Array.from(recordTypes);
  const exportKind = effectiveRecordTypes.length === 1 ? effectiveRecordTypes[0] : "mixed";
  const exportRow = await input.db.trainingExport.create({
    data: {
      id: exportId,
      kind: exportKind,
      status: "running",
      title,
      itemCount: records.length,
      configJson: JSON.stringify({
        mode,
        badCaseIds,
        annotatorId,
        reviewerId,
        notes,
      }),
    },
  });

  try {
    await input.db.$transaction(
      records.map((record, index) =>
        input.db.trainingExportItem.create({
          data: {
            trainingExportId: exportRow.id,
            badCaseId: itemMeta[index]?.badCaseId || null,
            sourceType:
              itemMeta[index]?.sourceType ||
              asString(asRecord((record as Record<string, unknown>).source)?.source_type) ||
              "unknown",
            sourceId:
              itemMeta[index]?.sourceId ||
              asOptionalString(asRecord((record as Record<string, unknown>).source)?.source_id),
            payloadJson: JSON.stringify(record),
          },
        })
      )
    );

    const bundle = await materializeExportBundle({
      exportId,
      title,
      recordTypes: effectiveRecordTypes as Array<"sft_candidate" | "preference_pair_candidate">,
      records,
    });

    const updated = await input.db.trainingExport.update({
      where: { id: exportRow.id },
      data: {
        status: "succeeded",
        outputPath: bundle.jsonlPath,
        summaryJson: JSON.stringify(bundle.manifest),
        itemCount: records.length,
      },
      include: { items: true },
    });

    return jsonResult({
      export: updated,
      outputDir: bundle.outputDir,
      jsonlPath: bundle.jsonlPath,
      manifestPath: bundle.manifestPath,
      readmePath: bundle.readmePath,
      skipped,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await input.db.trainingExport.update({
      where: { id: exportRow.id },
      data: {
        status: "failed",
        error: message,
      },
    });
    return jsonResult({ error: message, exportId: exportRow.id, skipped }, 500);
  }
}

export async function downloadTrainingExportService(input: {
  db: AgentDbClient;
  exportId: string;
}) {
  const exportRow = await input.db.trainingExport.findUnique({
    where: { id: input.exportId },
  });

  if (!exportRow || !exportRow.outputPath) {
    return jsonResult({ error: "Export not found" }, 404);
  }

  try {
    const body = await readFile(exportRow.outputPath, "utf-8");
    const filename = exportRow.outputPath.split("/").pop() || `${exportRow.id}.jsonl`;
    return jsonResult({
      body,
      filename,
      exportId: exportRow.id,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResult({ error: message }, 404);
  }
}
