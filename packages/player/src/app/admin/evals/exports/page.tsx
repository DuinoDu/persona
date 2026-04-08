import Link from "next/link";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { formatDateTime, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";

export const dynamic = "force-dynamic";

function parseJsonMaybe(value: string | null | undefined) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export default async function EvalExportsPage() {
  const exportRows = await prisma.trainingExport.findMany({
    orderBy: { createdAt: "desc" },
    take: 100,
    include: {
      items: { orderBy: { createdAt: "asc" } },
    },
  });

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">导出中心</div>
              <h1 className="text-2xl font-bold">Exports</h1>
              <p className="mt-1 text-sm text-gray-400">查看坏例导出的 JSONL、manifest 和下载入口。</p>
            </div>
            <AdminNav current="/admin/evals/exports" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/admin/evals" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              返回评测中心
            </Link>
            <Link href="/admin/evals/bad-cases" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              坏例列表
            </Link>
          </div>
        </header>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Export 列表</h2>
              <p className="text-sm text-gray-400">每条记录都能下载对应 JSONL 文件。</p>
            </div>
            <div className="text-sm text-gray-500">{exportRows.length} items</div>
          </div>

          {exportRows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">
              暂无导出记录
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-gray-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">Title</th>
                    <th className="px-3 py-2 font-medium">Kind</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Item Count</th>
                    <th className="px-3 py-2 font-medium">Output Path</th>
                    <th className="px-3 py-2 font-medium">Download</th>
                    <th className="px-3 py-2 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {exportRows.map((item) => {
                    const config = parseJsonMaybe(item.configJson) as Record<string, unknown> | null;
                    const modeText = typeof config?.mode === "string" ? config.mode : "";
                    const downloadHref = `/api/evals/exports/${item.id}/download`;
                    return (
                      <tr key={item.id} className="border-t border-gray-800 align-top">
                        <td className="px-3 py-3">
                          <div className="font-medium text-white">{item.title}</div>
                          <div className="mt-1 text-xs text-gray-500">{String(item.id)}</div>
                          {modeText && <div className="mt-1 text-xs text-gray-600">mode: {modeText}</div>}
                        </td>
                        <td className="px-3 py-3 text-gray-300">{item.kind}</td>
                        <td className="px-3 py-3">
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(item.status)}`}>
                            {item.status}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-gray-300">{item.itemCount}</td>
                        <td className="px-3 py-3 text-xs text-gray-500">{shortenPath(item.outputPath)}</td>
                        <td className="px-3 py-3">
                          {item.outputPath ? (
                            <a
                              href={downloadHref}
                              className="inline-flex rounded-lg bg-gray-800 px-3 py-2 text-xs text-gray-200 hover:bg-gray-700 transition"
                            >
                              Download JSONL
                            </a>
                          ) : (
                            <span className="text-xs text-gray-600">-</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-gray-400">
                          <div>{formatDateTime(item.createdAt)}</div>
                          <div className="mt-1 text-xs text-gray-600">更新: {formatDateTime(item.updatedAt)}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
