import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { BadCaseQuickCreate } from "@/components/evals/BadCaseQuickCreate";
import { IngestRunTracesButton } from "@/components/evals/IngestRunTracesButton";
import { formatDateTime, formatJsonText, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";
import {
  buildBatchTraceViewerId,
  loadGenerationRecordsFromRun,
  loadSummaryJsonTextFromRun,
} from "@ququ/agent/evalArtifacts";

export const dynamic = "force-dynamic";

export default async function EvalRunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await prisma.evalRun.findUnique({
    where: { id },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    notFound();
  }

  const configJson = formatJsonText(run.configJson);
  const generationRecords = await loadGenerationRecordsFromRun({
    outputDir: run.outputDir,
    inferHost: run.inferHost
      ? {
          sshHost: run.inferHost.sshHost,
          sshPort: run.inferHost.sshPort,
          sshUser: run.inferHost.sshUser,
          workspacePath: run.inferHost.workspacePath,
        }
      : null,
  });
  const remoteSummaryJson =
    !run.resultJson && run.summaryPath
      ? await loadSummaryJsonTextFromRun({
          summaryPath: run.summaryPath,
          inferHost: run.inferHost
            ? {
                sshHost: run.inferHost.sshHost,
                sshPort: run.inferHost.sshPort,
                sshUser: run.inferHost.sshUser,
                workspacePath: run.inferHost.workspacePath,
              }
            : null,
        })
      : null;
  const resultJson = formatJsonText(run.resultJson || remoteSummaryJson);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-6xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">Eval Run</div>
              <h1 className="text-2xl font-bold">{run.title}</h1>
              <p className="mt-1 text-sm text-gray-400">{run.id}</p>
            </div>
            <AdminNav current="/admin/evals" />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className={`inline-flex rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClass(run.status)}`}>{run.status}</span>
            <Link href="/admin/evals/runs/new" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              新建 Run
            </Link>
            <a href={`/api/evals/runs/${run.id}?refresh=1`} className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              刷新状态 JSON
            </a>
          </div>
        </header>

        <IngestRunTracesButton runId={run.id} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Infer Host</div>
            <div className="mt-2 text-lg font-semibold text-white">{run.inferHost?.name || "-"}</div>
            <div className="mt-1 text-xs text-gray-500">{run.inferHost ? `${run.inferHost.sshUser}@${run.inferHost.sshHost}:${run.inferHost.sshPort}` : "-"}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Deployment</div>
            <div className="mt-2 text-lg font-semibold text-white">{run.modelDeployment?.name || "-"}</div>
            <div className="mt-1 text-xs text-gray-500">{run.modelDeployment?.slug || "-"}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Suite</div>
            <div className="mt-2 text-lg font-semibold text-white">{run.evalSuite?.title || "-"}</div>
            <div className="mt-1 text-xs text-gray-500">{run.evalSuite?.slug || "-"}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Time</div>
            <div className="mt-2 text-sm text-white">创建: {formatDateTime(run.createdAt)}</div>
            <div className="mt-1 text-xs text-gray-500">更新: {formatDateTime(run.updatedAt)}</div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Remote Paths</h2>
            <div className="text-sm text-gray-300">tmux: <span className="text-gray-100">{run.tmuxSession || "-"}</span></div>
            <div className="text-sm text-gray-300">output: <span className="text-xs text-gray-500">{shortenPath(run.outputDir)}</span></div>
            <div className="text-sm text-gray-300">log: <span className="text-xs text-gray-500">{shortenPath(run.logPath)}</span></div>
            <div className="text-sm text-gray-300">status: <span className="text-xs text-gray-500">{shortenPath(run.statusPath)}</span></div>
            <div className="text-sm text-gray-300">summary: <span className="text-xs text-gray-500">{shortenPath(run.summaryPath)}</span></div>
            {run.error && <div className="rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200">{run.error}</div>}
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Remote Command</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{run.remoteCommand || "-"}</pre>
          </div>
        </section>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Case Results</h2>
              <p className="text-sm text-gray-400">每个 case 都可以下钻到 trace viewer。</p>
            </div>
            <div className="text-sm text-gray-500">{generationRecords.length} cases</div>
          </div>

          {generationRecords.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">
              暂无生成记录，或还未同步 generations.jsonl
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">Case ID</th>
                    <th className="px-3 py-2 font-medium">Slice</th>
                    <th className="px-3 py-2 font-medium">Output Preview</th>
                    <th className="px-3 py-2 font-medium">Tokens / Latency</th>
                    <th className="px-3 py-2 font-medium">Trace</th>
                    <th className="px-3 py-2 font-medium">Bad Case</th>
                  </tr>
                </thead>
                <tbody>
                  {generationRecords.map((record) => {
                    const tracePath = record.tracePath || (run.outputDir ? `${run.outputDir}/traces/${record.id}.json` : "");
                    const traceViewerHref = `/admin/evals/traces/${buildBatchTraceViewerId(run.id, record.id)}`;
                    return (
                      <tr key={record.id} className="border-t border-gray-800 align-top">
                        <td className="px-3 py-3">
                          <div className="font-medium text-white">{record.id}</div>
                          <div className="mt-1 text-xs text-gray-500">{record.tags.length > 0 ? record.tags.join(", ") : "-"}</div>
                        </td>
                        <td className="px-3 py-3 text-gray-300">{record.slice || "unspecified"}</td>
                        <td className="px-3 py-3 text-gray-300">
                          <div className="max-w-xl whitespace-pre-wrap text-xs leading-5 text-gray-200">
                            {record.cleanOutputText || record.rawOutputText || "-"}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-gray-300">
                          <div>{record.generatedTokens} tok</div>
                          <div className="mt-1 text-xs text-gray-500">{record.latencyMs} ms</div>
                        </td>
                        <td className="px-3 py-3 text-gray-300">
                          <div className="text-xs text-gray-500">{shortenPath(tracePath || null, 96)}</div>
                          <Link href={traceViewerHref} className="mt-2 inline-flex rounded-lg bg-gray-800 px-3 py-2 text-xs text-gray-200 hover:bg-gray-700 transition">
                            Open trace
                          </Link>
                        </td>
                        <td className="px-3 py-3 text-gray-300">
                          <BadCaseQuickCreate
                            sourceType="offline_case"
                            triggerLabel="标为 bad case"
                            title={`${run.title} / ${record.id}`}
                            defaultEvalRunId={run.id}
                            defaultCaseId={record.id}
                            defaultSourceId={record.id}
                            defaultSeverity="medium"
                            defaultNotes={`${run.title} / ${record.id}`}
                            defaultEditedTargetText={record.cleanOutputText || record.rawOutputText || ""}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Config JSON</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{configJson || "-"}</pre>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Result JSON</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{resultJson || "尚未写回 summary"}</pre>
          </div>
        </section>
      </div>
    </div>
  );
}
