import Link from "next/link";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { ArenaJudgeForm } from "@/components/evals/ArenaJudgeForm";
import { buildArenaComparisons, loadGenerationRecordsFromRun } from "@ququ/agent/evalArtifacts";
import { formatDateTime } from "@/lib/evalAdmin";

export const dynamic = "force-dynamic";

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] || "" : value || "";
}

function buildArenaHref(input: {
  suiteId?: string;
  leftRunId?: string;
  rightRunId?: string;
  caseId?: string;
}) {
  const params = new URLSearchParams();
  if (input.suiteId) params.set("suiteId", input.suiteId);
  if (input.leftRunId) params.set("leftRunId", input.leftRunId);
  if (input.rightRunId) params.set("rightRunId", input.rightRunId);
  if (input.caseId) params.set("caseId", input.caseId);
  const query = params.toString();
  return query ? `/admin/evals/arena?${query}` : "/admin/evals/arena";
}

function normalizePair(leftRunId: string, rightRunId: string) {
  if (!leftRunId || !rightRunId) {
    return [leftRunId, rightRunId] as const;
  }
  return leftRunId.localeCompare(rightRunId) <= 0
    ? ([leftRunId, rightRunId] as const)
    : ([rightRunId, leftRunId] as const);
}

function parseFailureTags(value: string | null | undefined) {
  if (!value) {
    return [] as string[];
  }
  try {
    const payload = JSON.parse(value);
    return Array.isArray(payload) ? payload.map((item) => String(item)).filter(Boolean) : [];
  } catch {
    return [] as string[];
  }
}

export default async function EvalArenaPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const runs = await prisma.evalRun.findMany({
    where: {
      status: "succeeded",
      outputDir: { not: null },
      evalSuiteId: { not: null },
    },
    include: {
      evalSuite: true,
      modelDeployment: true,
      inferHost: true,
    },
    orderBy: { createdAt: "desc" },
  });

  const suiteBuckets = new Map<
    string,
    {
      id: string;
      title: string;
      description: string | null;
      runs: typeof runs;
    }
  >();
  for (const run of runs) {
    if (!run.evalSuiteId || !run.evalSuite) {
      continue;
    }
    const bucket = suiteBuckets.get(run.evalSuiteId) || {
      id: run.evalSuiteId,
      title: run.evalSuite.title,
      description: run.evalSuite.description,
      runs: [],
    };
    bucket.runs.push(run);
    suiteBuckets.set(run.evalSuiteId, bucket);
  }

  const suites = Array.from(suiteBuckets.values()).sort((a, b) => a.title.localeCompare(b.title));
  const defaultSuite = suites.find((suite) => suite.runs.length >= 2) || suites[0] || null;
  const requestedSuiteId = firstParam(params.suiteId);
  const selectedSuiteId = requestedSuiteId && suiteBuckets.has(requestedSuiteId) ? requestedSuiteId : defaultSuite?.id || "";
  const selectedSuite = selectedSuiteId ? suiteBuckets.get(selectedSuiteId) || null : null;
  const suiteRuns = selectedSuite?.runs || [];

  let leftRunId = firstParam(params.leftRunId);
  if (!suiteRuns.some((run) => run.id === leftRunId)) {
    leftRunId = suiteRuns[0]?.id || "";
  }

  let rightRunId = firstParam(params.rightRunId);
  if (!suiteRuns.some((run) => run.id === rightRunId) || rightRunId === leftRunId) {
    rightRunId = suiteRuns.find((run) => run.id !== leftRunId)?.id || "";
  }

  [leftRunId, rightRunId] = normalizePair(leftRunId, rightRunId);
  const leftRun = suiteRuns.find((run) => run.id === leftRunId) || null;
  const rightRun = suiteRuns.find((run) => run.id === rightRunId) || null;

  let comparisons = [] as ReturnType<typeof buildArenaComparisons>;
  let judgmentsByCaseId = new Map<string, Awaited<ReturnType<typeof prisma.arenaJudgment.findMany>>[number]>();

  if (leftRun?.outputDir && rightRun?.outputDir) {
    const [leftRecords, rightRecords, judgments] = await Promise.all([
      loadGenerationRecordsFromRun({
        outputDir: leftRun.outputDir,
        inferHost: leftRun.inferHost
          ? {
              sshHost: leftRun.inferHost.sshHost,
              sshPort: leftRun.inferHost.sshPort,
              sshUser: leftRun.inferHost.sshUser,
              workspacePath: leftRun.inferHost.workspacePath,
            }
          : null,
      }),
      loadGenerationRecordsFromRun({
        outputDir: rightRun.outputDir,
        inferHost: rightRun.inferHost
          ? {
              sshHost: rightRun.inferHost.sshHost,
              sshPort: rightRun.inferHost.sshPort,
              sshUser: rightRun.inferHost.sshUser,
              workspacePath: rightRun.inferHost.workspacePath,
            }
          : null,
      }),
      prisma.arenaJudgment.findMany({
        where: {
          leftEvalRunId: leftRun.id,
          rightEvalRunId: rightRun.id,
        },
        orderBy: { updatedAt: "desc" },
      }),
    ]);
    comparisons = buildArenaComparisons({
      leftRunId: leftRun.id,
      rightRunId: rightRun.id,
      leftRecords,
      rightRecords,
    });
    judgmentsByCaseId = new Map(judgments.map((item) => [item.caseId, item]));
  }

  const requestedCaseId = firstParam(params.caseId);
  const selectedCaseId = comparisons.some((item) => item.caseId === requestedCaseId)
    ? requestedCaseId
    : comparisons[0]?.caseId || "";
  const currentCase = comparisons.find((item) => item.caseId === selectedCaseId) || null;
  const currentJudgment = selectedCaseId ? judgmentsByCaseId.get(selectedCaseId) || null : null;
  const judgedCount = comparisons.filter((item) => judgmentsByCaseId.has(item.caseId)).length;

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">盲评 Arena</div>
              <h1 className="text-2xl font-bold">Eval Arena</h1>
              <p className="mt-1 text-sm text-gray-400">选择同一 suite 下的两个离线 run，对同 case 输出做 A / B 盲评。</p>
            </div>
            <AdminNav current="/admin/evals/arena" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/admin/evals" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              返回评测中心
            </Link>
            <Link href="/admin/evals/runs/new" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              新建 Eval Run
            </Link>
          </div>
        </header>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-white">选择比较对象</h2>
            <p className="mt-1 text-sm text-gray-400">Arena 目前要求两个 run 都已经成功完成，并且有 `generations.jsonl` 输出。</p>
          </div>

          {suites.length === 0 ? (
            <div className="rounded-lg bg-amber-600/20 px-4 py-3 text-sm text-amber-100">还没有可用的离线 run。先完成至少两次同 suite 的离线 eval。</div>
          ) : (
            <form method="GET" className="grid gap-3 lg:grid-cols-[1fr,1fr,1fr,auto]">
              <label className="space-y-2">
                <div className="text-sm text-gray-300">Suite</div>
                <select name="suiteId" defaultValue={selectedSuiteId} className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
                  {suites.map((suite) => (
                    <option key={suite.id} value={suite.id}>
                      {suite.title} ({suite.runs.length})
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2">
                <div className="text-sm text-gray-300">Run A</div>
                <select name="leftRunId" defaultValue={leftRunId} className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
                  {suiteRuns.map((run) => (
                    <option key={run.id} value={run.id}>
                      {run.title} · {run.modelDeployment?.name || "-"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2">
                <div className="text-sm text-gray-300">Run B</div>
                <select name="rightRunId" defaultValue={rightRunId} className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
                  {suiteRuns.map((run) => (
                    <option key={run.id} value={run.id}>
                      {run.title} · {run.modelDeployment?.name || "-"}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-end">
                <button className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white">加载 Arena</button>
              </div>
            </form>
          )}
        </section>

        {leftRun && rightRun ? (
          <section className="grid gap-4 md:grid-cols-4">
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">Suite</div>
              <div className="mt-2 text-lg font-semibold text-white">{selectedSuite?.title || "-"}</div>
              <div className="mt-1 text-xs text-gray-500">{selectedSuite?.description || "-"}</div>
            </div>
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">Left Run</div>
              <div className="mt-2 text-sm font-semibold text-white">{leftRun.title}</div>
              <div className="mt-1 text-xs text-gray-500">{leftRun.modelDeployment?.name || "-"}</div>
            </div>
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">Right Run</div>
              <div className="mt-2 text-sm font-semibold text-white">{rightRun.title}</div>
              <div className="mt-1 text-xs text-gray-500">{rightRun.modelDeployment?.name || "-"}</div>
            </div>
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">Judged / Total</div>
              <div className="mt-2 text-3xl font-semibold text-white">{judgedCount} / {comparisons.length}</div>
              <div className="mt-1 text-xs text-gray-500">最近更新：{formatDateTime((currentJudgment || leftRun).updatedAt)}</div>
            </div>
          </section>
        ) : null}

        {leftRun && rightRun && comparisons.length === 0 ? (
          <div className="rounded-xl border border-amber-600/30 bg-amber-600/10 px-5 py-4 text-sm text-amber-100">
            当前这对 run 没有可比较的 case。常见原因是 `generations.jsonl` 缺失，或者两个 run 不是同一个 suite 产物。
          </div>
        ) : null}

        {comparisons.length > 0 ? (
          <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Case 导航</h2>
                <p className="mt-1 text-sm text-gray-400">绿色代表已打分，蓝色代表当前 case。</p>
              </div>
              <div className="text-xs text-gray-500">common cases: {comparisons.length}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              {comparisons.map((item) => {
                const active = item.caseId === selectedCaseId;
                const judged = judgmentsByCaseId.has(item.caseId);
                const className = [
                  "rounded-lg border px-3 py-2 text-xs transition",
                  active
                    ? "border-blue-500 bg-blue-500/10 text-blue-100"
                    : judged
                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-100"
                      : "border-gray-800 bg-gray-950 text-gray-300 hover:border-gray-700",
                ].join(" ");
                return (
                  <Link
                    key={item.caseId}
                    href={buildArenaHref({
                      suiteId: selectedSuiteId,
                      leftRunId: leftRunId,
                      rightRunId: rightRunId,
                      caseId: item.caseId,
                    })}
                    className={className}
                  >
                    <div className="font-medium">{item.caseId}</div>
                    <div className="mt-1 text-[11px] opacity-80">{item.caseSlice}</div>
                  </Link>
                );
              })}
            </div>
          </section>
        ) : null}

        {currentCase ? (
          <>
            <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
              <div>
                <div className="text-sm text-gray-400">Case</div>
                <h2 className="text-xl font-semibold text-white">{currentCase.caseId}</h2>
                <p className="mt-1 text-sm text-gray-400">slice: {currentCase.caseSlice || "unspecified"}</p>
              </div>
              <div className="rounded-lg bg-gray-950 px-4 py-3 text-sm text-gray-300">{currentCase.promptPreview || "-"}</div>
              <div className="space-y-3">
                {currentCase.messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className="rounded-lg border border-gray-800 bg-gray-950 px-4 py-3">
                    <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{message.role}</div>
                    <div className="whitespace-pre-wrap break-words text-sm text-gray-200">{message.content}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              {[{ label: "A", slot: currentCase.slotA }, { label: "B", slot: currentCase.slotB }].map((item) => (
                <div key={item.label} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-xl font-semibold text-white">Output {item.label}</h2>
                    <div className="text-xs text-gray-500">
                      {item.slot.generatedTokens} tokens · {item.slot.latencyMs} ms
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={item.slot.blankOutput ? "rounded-full bg-red-600/20 px-2.5 py-1 text-red-200" : "rounded-full bg-gray-800 px-2.5 py-1 text-gray-300"}>blank={String(item.slot.blankOutput)}</span>
                    <span className={item.slot.shortOutput ? "rounded-full bg-amber-600/20 px-2.5 py-1 text-amber-100" : "rounded-full bg-gray-800 px-2.5 py-1 text-gray-300"}>short={String(item.slot.shortOutput)}</span>
                    <span className={item.slot.containsControlTokens ? "rounded-full bg-red-600/20 px-2.5 py-1 text-red-200" : "rounded-full bg-gray-800 px-2.5 py-1 text-gray-300"}>control={String(item.slot.containsControlTokens)}</span>
                  </div>
                  <div className="min-h-72 whitespace-pre-wrap break-words rounded-lg bg-gray-950 px-4 py-4 text-sm text-gray-100">
                    {item.slot.outputText || "<empty>"}
                  </div>
                </div>
              ))}
            </section>

            <ArenaJudgeForm
              evalSuiteId={selectedSuiteId || null}
              leftEvalRunId={leftRunId}
              rightEvalRunId={rightRunId}
              caseId={currentCase.caseId}
              caseSlice={currentCase.caseSlice}
              promptPreview={currentCase.promptPreview}
              existingJudgment={
                currentJudgment
                  ? {
                      winner: currentJudgment.winner,
                      winnerEvalRunId: currentJudgment.winnerEvalRunId,
                      personaScore: currentJudgment.personaScore,
                      judgmentScore: currentJudgment.judgmentScore,
                      premiseScore: currentJudgment.premiseScore,
                      structureScore: currentJudgment.structureScore,
                      actionabilityScore: currentJudgment.actionabilityScore,
                      naturalnessScore: currentJudgment.naturalnessScore,
                      stabilityScore: currentJudgment.stabilityScore,
                      failureTags: parseFailureTags(currentJudgment.failureTagsJson),
                      notes: currentJudgment.notes,
                      updatedAt: currentJudgment.updatedAt.toISOString(),
                    }
                  : null
              }
            />
          </>
        ) : null}
      </div>
    </div>
  );
}
