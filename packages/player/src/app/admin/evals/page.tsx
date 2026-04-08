import Link from "next/link";
import { AdminNav } from "@/components/AdminNav";
import {
  formatDateTime,
  severityBadgeClass,
  shortenPath,
  statusBadgeClass,
} from "@/lib/evalAdmin";
import { getEvalDashboardOverview } from "@/lib/evalDashboard";

export const dynamic = "force-dynamic";

function MetricRow({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "good" | "warn" | "bad" }) {
  const valueClass =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-200"
        : tone === "bad"
          ? "text-rose-300"
          : "text-white";
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-gray-950/60 px-3 py-2">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
}

export default async function EvalAdminPage() {
  const overview = await getEvalDashboardOverview();

  const cards = [
    {
      label: "Infer Hosts",
      value: overview.totals.inferHosts,
      hint: `${overview.totals.deployments} deployments`,
    },
    {
      label: "Eval Suites",
      value: overview.totals.evalSuites,
      hint: `${overview.runs.last7d} runs / 7d`,
    },
    {
      label: "Eval Runs",
      value: overview.totals.evalRuns,
      hint: `${overview.runs.running + overview.runs.queued} active`,
    },
    {
      label: "Live Sessions",
      value: overview.totals.liveSessions,
      hint: `${overview.live.activeSessions} active`,
    },
    {
      label: "Inference Traces",
      value: overview.totals.inferenceTraces,
      hint: `${overview.traces.last7d} / 7d`,
    },
    {
      label: "Bad Cases",
      value: overview.totals.badCases,
      hint: `${overview.flywheel.openBadCases} open`,
    },
    {
      label: "Exports",
      value: overview.totals.exports,
      hint: `${overview.flywheel.succeededExports} succeeded`,
    },
    {
      label: "Export Items",
      value: overview.flywheel.exportItems,
      hint: `${overview.flywheel.exportedBadCases} bad cases exported`,
    },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">评测后台</div>
              <h1 className="text-2xl font-bold">Eval Center</h1>
              <p className="mt-1 text-sm text-gray-400">管理推理 H20、离线评测任务和在线 infer 入口。</p>
            </div>
            <AdminNav current="/admin/evals" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/admin/infer/endpoints" className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition">
              配置推理端点
            </Link>
            <Link href="/admin/evals/runs/new" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              新建离线评测 Run
            </Link>
            <Link href="/admin/evals/live" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              在线 Infer 面板
            </Link>
            <Link href="/admin/evals/bad-cases" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              评测坏例
            </Link>
            <Link href="/admin/evals/exports" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              导出
            </Link>
            <Link href={'/admin/evals/arena'} className={'rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition'}>
              Arena 盲评
            </Link>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {cards.map((card) => (
            <div key={card.label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">{card.label}</div>
              <div className="mt-2 text-3xl font-semibold text-white">{card.value}</div>
              <div className="mt-2 text-xs text-gray-500">{card.hint}</div>
            </div>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Offline Eval Health</h2>
              <p className="mt-1 text-sm text-gray-400">看 batch run 当前是否在稳定产出。</p>
            </div>
            <div className="space-y-2">
              <MetricRow label="running" value={overview.runs.running} tone="good" />
              <MetricRow label="queued" value={overview.runs.queued} tone="warn" />
              <MetricRow label="draft" value={overview.runs.draft} />
              <MetricRow label="succeeded" value={overview.runs.succeeded} tone="good" />
              <MetricRow label="failed / error" value={overview.runs.failed} tone="bad" />
              <MetricRow label="created in 7d" value={overview.runs.last7d} />
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Live Infer Health</h2>
              <p className="mt-1 text-sm text-gray-400">关注 live session 和 H20 常驻服务状态。</p>
            </div>
            <div className="space-y-2">
              <MetricRow label="active sessions" value={overview.live.activeSessions} tone="good" />
              <MetricRow label="draft sessions" value={overview.live.draftSessions} />
              <MetricRow label="sessions updated / 7d" value={overview.live.sessionsLast7d} />
              <MetricRow label="ready services" value={overview.live.readyServices} tone="good" />
              <MetricRow label="starting services" value={overview.live.startingServices} tone="warn" />
              <MetricRow label="failed services" value={overview.live.failedServices} tone="bad" />
              <MetricRow label="stopped services" value={overview.live.stoppedServices} />
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Trace Coverage</h2>
              <p className="mt-1 text-sm text-gray-400">确认 online / offline trace 是否都在沉淀。</p>
            </div>
            <div className="space-y-2">
              <MetricRow label="offline_case traces" value={overview.traces.offline} tone="good" />
              <MetricRow label="live_turn traces" value={overview.traces.live} tone="good" />
              <MetricRow label="arena traces" value={overview.traces.arena} />
              <MetricRow label="error traces" value={overview.traces.errors} tone="bad" />
              <MetricRow label="traces created / 7d" value={overview.traces.last7d} />
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Data Flywheel</h2>
              <p className="mt-1 text-sm text-gray-400">看坏例回流、导出和训练样本沉淀是否顺畅。</p>
            </div>
            <div className="space-y-2">
              <MetricRow label="open bad cases" value={overview.flywheel.openBadCases} tone="warn" />
              <MetricRow label="high / critical" value={overview.flywheel.highSeverityBadCases} tone="bad" />
              <MetricRow label="export-ready bad cases" value={overview.flywheel.exportReadyBadCases} tone="good" />
              <MetricRow label="exported bad cases" value={overview.flywheel.exportedBadCases} tone="good" />
              <MetricRow label="bad cases created / 7d" value={overview.flywheel.badCasesLast7d} />
              <MetricRow label="succeeded exports" value={overview.flywheel.succeededExports} tone="good" />
              <MetricRow label="running exports" value={overview.flywheel.runningExports} tone="warn" />
              <MetricRow label="failed exports" value={overview.flywheel.failedExports} tone="bad" />
              <MetricRow label="exports created / 7d" value={overview.flywheel.exportsLast7d} />
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">最近 Eval Runs</h2>
              <p className="text-sm text-gray-400">当前重点是离线 batch eval，在线 infer 模块会接在这里。</p>
            </div>
            <Link href="/admin/evals/runs/new" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              创建 Run
            </Link>
          </div>

          {overview.recentRuns.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">暂无 Eval Run</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">标题</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">Host / Deployment</th>
                    <th className="px-3 py-2 font-medium">Suite</th>
                    <th className="px-3 py-2 font-medium">输出</th>
                    <th className="px-3 py-2 font-medium">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.recentRuns.map((run) => (
                    <tr key={run.id} className="border-t border-gray-800 align-top">
                      <td className="px-3 py-3">
                        <Link href={`/admin/evals/runs/${run.id}`} className="font-medium text-white hover:text-blue-300">
                          {run.title}
                        </Link>
                        <div className="mt-1 text-xs text-gray-500">{run.id}</div>
                      </td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(run.status)}`}>
                          {run.status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-gray-300">
                        <div>{run.inferHost?.name || "-"}</div>
                        <div className="mt-1 text-xs text-gray-500">{run.modelDeployment?.name || "-"}</div>
                      </td>
                      <td className="px-3 py-3 text-gray-300">
                        <div>{run.evalSuite?.title || "-"}</div>
                        <div className="mt-1 text-xs text-gray-500">{run.evalSuite?.slug || "-"}</div>
                      </td>
                      <td className="px-3 py-3 text-xs text-gray-500">{shortenPath(run.outputDir)}</td>
                      <td className="px-3 py-3 text-gray-400">
                        <div>{formatDateTime(run.createdAt)}</div>
                        <div className="mt-1 text-xs text-gray-600">更新: {formatDateTime(run.updatedAt)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">最近 Bad Cases</h2>
                <p className="text-sm text-gray-400">优先关注 open + high severity 的问题。</p>
              </div>
              <Link href="/admin/evals/bad-cases" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
                打开坏例列表
              </Link>
            </div>

            {overview.recentBadCases.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">
                暂无 bad case
              </div>
            ) : (
              <div className="space-y-3">
                {overview.recentBadCases.map((badCase) => (
                  <div key={badCase.id} className="rounded-lg border border-gray-800 bg-gray-950/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-medium text-white">{badCase.title || badCase.id}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          {badCase.sourceType}
                          {badCase.caseId ? ` / case:${badCase.caseId}` : ""}
                          {badCase.sourceId ? ` / ${badCase.sourceId}` : ""}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(badCase.status)}`}>
                          {badCase.status}
                        </span>
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${severityBadgeClass(badCase.severity)}`}>
                          {badCase.severity}
                        </span>
                      </div>
                    </div>

                    <div className="mt-3 text-xs text-gray-400">
                      deployment: {badCase.modelDeployment?.name || "-"} · run: {badCase.evalRun?.title || "-"} · session: {badCase.liveSession?.title || "-"}
                    </div>

                    {badCase.notes ? (
                      <div className="mt-2 max-w-3xl whitespace-pre-wrap text-sm text-gray-300">{badCase.notes}</div>
                    ) : null}

                    <div className="mt-3 flex flex-wrap gap-3 text-xs">
                      {badCase.evalRunId ? (
                        <Link href={`/admin/evals/runs/${badCase.evalRunId}`} className="text-blue-300 hover:text-blue-200">
                          查看 Run
                        </Link>
                      ) : null}
                      {badCase.liveSessionId ? (
                        <Link href="/admin/evals/live" className="text-blue-300 hover:text-blue-200">
                          查看 Live
                        </Link>
                      ) : null}
                      <Link href="/admin/evals/bad-cases" className="text-blue-300 hover:text-blue-200">
                        打开 Bad Case 列表
                      </Link>
                      <span className="text-gray-600">更新: {formatDateTime(badCase.updatedAt)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">最近 Exports</h2>
                <p className="text-sm text-gray-400">检查训练导出是否成功落盘、是否需要回看失败任务。</p>
              </div>
              <Link href="/admin/evals/exports" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
                打开导出列表
              </Link>
            </div>

            {overview.recentExports.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">
                暂无 export
              </div>
            ) : (
              <div className="space-y-3">
                {overview.recentExports.map((item) => (
                  <div key={item.id} className="rounded-lg border border-gray-800 bg-gray-950/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-medium text-white">{item.title}</div>
                        <div className="mt-1 text-xs text-gray-500">{item.kind}</div>
                      </div>
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(item.status)}`}>
                        {item.status}
                      </span>
                    </div>

                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg bg-gray-900/80 px-3 py-2 text-xs text-gray-300">
                        itemCount: <span className="text-gray-100">{item.itemCount}</span>
                      </div>
                      <div className="rounded-lg bg-gray-900/80 px-3 py-2 text-xs text-gray-300">
                        exportItems: <span className="text-gray-100">{item._count.items}</span>
                      </div>
                    </div>

                    <div className="mt-3 text-xs text-gray-500">{shortenPath(item.outputPath, 96)}</div>
                    {item.error ? (
                      <div className="mt-3 rounded-lg bg-red-600/20 px-3 py-2 text-sm text-red-200">{item.error}</div>
                    ) : null}

                    <div className="mt-3 flex flex-wrap gap-3 text-xs">
                      <Link href="/admin/evals/exports" className="text-blue-300 hover:text-blue-200">
                        查看 Exports
                      </Link>
                      {item.outputPath ? (
                        <a href={`/api/evals/exports/${item.id}/download`} className="text-blue-300 hover:text-blue-200">
                          下载 JSONL
                        </a>
                      ) : null}
                      <span className="text-gray-600">更新: {formatDateTime(item.updatedAt)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
