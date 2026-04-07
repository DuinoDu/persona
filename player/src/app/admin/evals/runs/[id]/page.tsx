import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { formatDateTime, formatJsonText, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";

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
  const resultJson = formatJsonText(run.resultJson);

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
