import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { SetupPanel } from "@/components/evals/SetupPanel";
import { formatDateTime, statusBadgeClass, shortenPath } from "@/lib/evalAdmin";

export const dynamic = "force-dynamic";

export default async function InferEndpointsPage() {
  const [hosts, deployments, suites] = await Promise.all([
    prisma.inferHost.findMany({ orderBy: { createdAt: "desc" } }),
    prisma.modelDeployment.findMany({ orderBy: { createdAt: "desc" }, include: { inferHost: true } }),
    prisma.evalSuite.findMany({ orderBy: { createdAt: "desc" } }),
  ]);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">推理资源配置</div>
              <h1 className="text-2xl font-bold">Infer Endpoints</h1>
              <p className="mt-1 text-sm text-gray-400">维护 H20 主机、部署信息和固定评测集元数据。</p>
            </div>
            <AdminNav current="/admin/infer/endpoints" />
          </div>
        </header>

        <SetupPanel hosts={hosts.map((host) => ({ id: host.id, name: host.name }))} />

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-white">Hosts</h2>
          {hosts.length === 0 ? <div className="text-sm text-gray-400">暂无 Host</div> : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">名称</th>
                    <th className="px-3 py-2 font-medium">SSH</th>
                    <th className="px-3 py-2 font-medium">Workspace</th>
                    <th className="px-3 py-2 font-medium">策略</th>
                    <th className="px-3 py-2 font-medium">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {hosts.map((host) => (
                    <tr key={host.id} className="border-t border-gray-800 align-top">
                      <td className="px-3 py-3">
                        <div className="font-medium text-white">{host.name}</div>
                        <div className="mt-1 text-xs text-gray-500">{host.id}</div>
                      </td>
                      <td className="px-3 py-3 text-gray-300">{host.sshUser}@{host.sshHost}:{host.sshPort}</td>
                      <td className="px-3 py-3 text-xs text-gray-500">{shortenPath(host.workspacePath)}</td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(host.status)}`}>{host.gpuPolicy}</span>
                      </td>
                      <td className="px-3 py-3 text-gray-400">{formatDateTime(host.createdAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-white">Deployments</h2>
          {deployments.length === 0 ? <div className="text-sm text-gray-400">暂无 Deployment</div> : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">名称</th>
                    <th className="px-3 py-2 font-medium">Host</th>
                    <th className="px-3 py-2 font-medium">Model</th>
                    <th className="px-3 py-2 font-medium">Service</th>
                    <th className="px-3 py-2 font-medium">Runner</th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.map((deployment) => (
                    <tr key={deployment.id} className="border-t border-gray-800 align-top">
                      <td className="px-3 py-3">
                        <div className="font-medium text-white">{deployment.name}</div>
                        <div className="mt-1 text-xs text-gray-500">{deployment.slug}</div>
                      </td>
                      <td className="px-3 py-3 text-gray-300">{deployment.inferHost.name}</td>
                      <td className="px-3 py-3 text-xs text-gray-500">
                        <div>{shortenPath(deployment.baseModelPath)}</div>
                        <div className="mt-1">adapter: {shortenPath(deployment.adapterPath)}</div>
                      </td>
                      <td className="px-3 py-3 text-gray-300">
                        <div>{deployment.serviceMode}</div>
                        <div className="mt-1 text-xs text-gray-500">{deployment.serviceStatus}</div>
                      </td>
                      <td className="px-3 py-3 text-xs text-gray-500">{shortenPath(deployment.runnerScriptPath)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <h2 className="text-lg font-semibold text-white">Eval Suites</h2>
          {suites.length === 0 ? <div className="text-sm text-gray-400">暂无 Suite</div> : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">标题</th>
                    <th className="px-3 py-2 font-medium">Slug</th>
                    <th className="px-3 py-2 font-medium">Cases</th>
                    <th className="px-3 py-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {suites.map((suite) => (
                    <tr key={suite.id} className="border-t border-gray-800 align-top">
                      <td className="px-3 py-3 text-white">{suite.title}</td>
                      <td className="px-3 py-3 text-gray-400">{suite.slug}</td>
                      <td className="px-3 py-3 text-gray-300">{suite.caseCount}</td>
                      <td className="px-3 py-3 text-xs text-gray-500">{shortenPath(suite.sourcePath)}</td>
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
