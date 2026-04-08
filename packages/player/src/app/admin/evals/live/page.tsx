import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { LiveInferConsole } from "@/components/evals/LiveInferConsole";

export const dynamic = "force-dynamic";

export default async function EvalLivePage() {
  const [deployments, sessions] = await Promise.all([
    prisma.modelDeployment.findMany({
      where: { serviceMode: { not: "offline_only" } },
      orderBy: { createdAt: "desc" },
      include: { inferHost: true },
    }),
    prisma.liveSession.findMany({
      orderBy: { updatedAt: "desc" },
      take: 20,
      include: {
        inferHost: true,
        modelDeployment: true,
        turns: { orderBy: { createdAt: "asc" } },
      },
    }),
  ]);

  const deploymentItems = deployments.map((item) => ({
    id: item.id,
    name: item.name,
    slug: item.slug,
    inferHostName: item.inferHost.name,
    inferHostId: item.inferHostId,
    serviceMode: item.serviceMode,
    serviceStatus: item.serviceStatus,
    serviceBaseUrl: item.serviceBaseUrl,
    serviceChatPath: item.serviceChatPath,
    serviceStreamPath: item.serviceStreamPath,
    serviceSessionName: item.serviceSessionName,
    serviceLogPath: item.serviceLogPath,
    serviceStatusPath: item.serviceStatusPath,
    serviceLastExitCode: item.serviceLastExitCode,
    serviceLastError: item.serviceLastError,
    serviceLastHealthJson: item.serviceLastHealthJson,
    serviceLastCheckedAt: item.serviceLastCheckedAt ? item.serviceLastCheckedAt.toISOString() : null,
    notes: item.notes,
  }));

  const sessionItems = sessions.map((item) => ({
    id: item.id,
    title: item.title,
    status: item.status,
    scenario: item.scenario,
    notes: item.notes,
    inferHostId: item.inferHostId,
    modelDeploymentId: item.modelDeploymentId,
    modelDeploymentName: item.modelDeployment?.name || null,
    inferHostName: item.inferHost?.name || null,
    createdAt: item.createdAt.toISOString(),
    updatedAt: item.updatedAt.toISOString(),
    turns: item.turns.map((turn) => ({
      id: turn.id,
      role: turn.role,
      content: turn.content,
      latencyMs: turn.latencyMs,
      tokenCount: turn.tokenCount,
      createdAt: turn.createdAt.toISOString(),
    })),
  }));

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">在线推理</div>
              <h1 className="text-2xl font-bold">Live Infer</h1>
              <p className="mt-1 text-sm text-gray-400">通过 H20 启动常驻推理服务，模拟连麦场景做多轮对话和快速人工质检。</p>
            </div>
            <AdminNav current="/admin/evals/live" />
          </div>
        </header>

        <LiveInferConsole deployments={deploymentItems} initialSessions={sessionItems} />
      </div>
    </div>
  );
}
