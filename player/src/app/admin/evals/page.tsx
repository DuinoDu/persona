import Link from "next/link";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { formatDateTime, statusBadgeClass, shortenPath } from "@/lib/evalAdmin";

export const dynamic = "force-dynamic";

export default async function EvalAdminPage() {
  const [hostCount, deploymentCount, suiteCount, runCount, liveCount, recentRuns] = await Promise.all([
    prisma.inferHost.count(),
    prisma.modelDeployment.count(),
    prisma.evalSuite.count(),
    prisma.evalRun.count(),
    prisma.liveSession.count(),
    prisma.evalRun.findMany({
      orderBy: { createdAt: "desc" },
      take: 20,
      include: {
        inferHost: true,
        modelDeployment: true,
        evalSuite: true,
      },
    }),
  ]);

  const cards = [
    { label: "Infer Hosts", value: hostCount },
    { label: "Deployments", value: deploymentCount },
    { label: "Eval Suites", value: suiteCount },
    { label: "Eval Runs", value: runCount },
    { label: "Live Sessions", value: liveCount },
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
            <Link href={'/admin/evals/arena'} className={'rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition'}>
              Arena 盲评
            </Link>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-5">
          {cards.map((card) => (
            <div key={card.label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="text-sm text-gray-400">{card.label}</div>
              <div className="mt-2 text-3xl font-semibold text-white">{card.value}</div>
            </div>
          ))}
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

          {recentRuns.length === 0 ? (
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
                  {recentRuns.map((run) => (
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
      </div>
    </div>
  );
}
