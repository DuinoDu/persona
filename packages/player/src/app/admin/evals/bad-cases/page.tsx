import Link from "next/link";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { BadCaseExportPanel } from "@/components/evals/BadCaseExportPanel";

export const dynamic = "force-dynamic";

function asJsonArray(value: string | null | undefined) {
  if (!value) return [] as string[];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map((item) => String(item)).filter(Boolean) : [];
  } catch {
    return [] as string[];
  }
}

export default async function EvalBadCasesPage() {
  const badCases = await prisma.badCase.findMany({
    orderBy: { createdAt: "desc" },
    take: 100,
    include: {
      inferHost: true,
      modelDeployment: true,
      evalRun: true,
      liveSession: { include: { inferHost: true, modelDeployment: true } },
      liveTurn: true,
      inferenceTrace: true,
    },
  });

  const items = badCases.map((item) => ({
    id: item.id,
    status: item.status,
    severity: item.severity,
    title: item.title || item.id,
    sourceType: item.sourceType,
    sourceId: item.sourceId,
    caseId: item.caseId,
    failureTags: asJsonArray(item.failureTagsJson),
    notes: item.notes,
    modelDeploymentSlug: item.modelDeployment?.slug || null,
    evalRunId: item.evalRunId,
    evalRunTitle: item.evalRun?.title || null,
    liveSessionTitle: item.liveSession?.title || null,
    liveSessionId: item.liveSessionId,
    traceHref:
      item.inferenceTrace && item.evalRunId && item.caseId
        ? `/admin/evals/traces/${item.evalRunId}::${encodeURIComponent(item.caseId)}`
        : null,
    createdAt: item.createdAt.toISOString(),
    updatedAt: item.updatedAt.toISOString(),
  }));

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">评测坏例</div>
              <h1 className="text-2xl font-bold">Bad Cases</h1>
              <p className="mt-1 text-sm text-gray-400">集中查看线上和离线评测中标记出来的问题样本，并支持直接批量导出。</p>
            </div>
            <AdminNav current="/admin/evals/bad-cases" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/admin/evals" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              返回评测中心
            </Link>
            <Link href="/admin/evals/exports" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              导出列表
            </Link>
          </div>
        </header>

        <BadCaseExportPanel items={items} />
      </div>
    </div>
  );
}
