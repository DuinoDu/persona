import Link from "next/link";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { CreateEvalRunForm } from "@/components/evals/CreateEvalRunForm";

export const dynamic = "force-dynamic";

export default async function NewEvalRunPage() {
  const [hosts, deployments, suites] = await Promise.all([
    prisma.inferHost.findMany({ orderBy: { createdAt: "desc" } }),
    prisma.modelDeployment.findMany({ orderBy: { createdAt: "desc" } }),
    prisma.evalSuite.findMany({ orderBy: { createdAt: "desc" } }),
  ]);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">离线评测</div>
              <h1 className="text-2xl font-bold">New Eval Run</h1>
              <p className="mt-1 text-sm text-gray-400">当前会通过 SSH 到推理 H20，并在远端 `tmux` 中启动 batch infer。</p>
            </div>
            <AdminNav current="/admin/evals" />
          </div>
        </header>

        <CreateEvalRunForm
          hosts={hosts.map((item) => ({ id: item.id, label: `${item.name} (${item.sshHost}:${item.sshPort})` }))}
          deployments={deployments.map((item) => ({ id: item.id, label: item.name }))}
          suites={suites.map((item) => ({ id: item.id, label: `${item.title} (${item.caseCount})` }))}
        />

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 text-sm text-gray-300">
          <p>推荐先用样例 suite 跑通链路，再接正式的固定评测集。</p>
          <div className="mt-2 text-xs text-gray-500">样例 suite: /vita-vepfs-data/fileset1/usr_data/yueyu/ws/persona/artifacts/evals/suites/persona_baseline_smoke_v1.jsonl</div>
          <div className="mt-4">
            <Link href="/admin/infer/endpoints" className="text-blue-300 hover:text-blue-200">还没配置 Host / Deployment / Suite？先去配置。</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
