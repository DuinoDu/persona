import Link from "next/link";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function formatDateTime(value: Date | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(value);
}

function formatSubtitleRange(start: number | null, end: number | null) {
  const formatPart = (input: number | null) => {
    if (typeof input !== "number" || !Number.isFinite(input)) return "--";
    const totalSeconds = Math.max(0, Math.floor(input));
    const hours = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;
    if (hours > 0) {
      return `${hours}:${mins.toString().padStart(2, "0")}:${secs
        .toString()
        .padStart(2, "0")}`;
    }
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return `${formatPart(start)} - ${formatPart(end)}`;
}

function statusBadgeClass(status: string) {
  switch (status) {
    case "applied":
      return "bg-green-600/20 text-green-300";
    case "reverted":
      return "bg-orange-600/20 text-orange-200";
    case "running":
      return "bg-blue-600/20 text-blue-300";
    case "needs_human":
      return "bg-yellow-600/20 text-yellow-200";
    case "rejected":
      return "bg-gray-600/20 text-gray-300";
    case "failed":
      return "bg-red-600/20 text-red-300";
    default:
      return "bg-gray-700/40 text-gray-300";
  }
}

function processingBadgeClass(status: string) {
  switch (status) {
    case "已处理":
      return "bg-emerald-600/20 text-emerald-300";
    case "处理中":
      return "bg-sky-600/20 text-sky-300";
    default:
      return "bg-gray-700/40 text-gray-300";
  }
}

function formatPatchJson(value: string | null) {
  if (!value) return null;
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

export default async function FeedbackAdminPage() {
  const [feedbacks, total] = await Promise.all([
    prisma.feedback.findMany({
      orderBy: { createdAt: "desc" },
      take: 200,
      include: {
        repairJobs: {
          orderBy: { createdAt: "desc" },
          take: 1,
        },
      },
    }),
    prisma.feedback.count(),
  ]);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm text-gray-400">后台管理</div>
            <h1 className="text-2xl font-bold">反馈列表</h1>
            <p className="mt-1 text-sm text-gray-400">共 {total} 条，当前显示最新 {feedbacks.length} 条</p>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="/api/feedback/export"
              className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 transition"
            >
              导出 CSV
            </a>
            <Link
              href="/admin/evals"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition"
            >
              评测中心
            </Link>
            <Link
              href="/"
              className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
            >
              返回播放器
            </Link>
          </div>
        </header>

        {feedbacks.length === 0 ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center text-gray-400">
            暂无反馈
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-800/80 text-gray-300">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">时间</th>
                  <th className="px-4 py-3 text-left font-medium">处理状态</th>
                  <th className="px-4 py-3 text-left font-medium">音频</th>
                  <th className="px-4 py-3 text-left font-medium">字幕</th>
                  <th className="px-4 py-3 text-left font-medium">反馈 / 修复结果</th>
                </tr>
              </thead>
              <tbody>
                {feedbacks.map((item) => {
                  const latestJob = item.repairJobs[0] ?? null;
                  const patchJson = formatPatchJson(item.repairPatchJson);
                  return (
                    <tr key={item.id} className="border-t border-gray-800 align-top">
                      <td className="px-4 py-3 whitespace-nowrap text-gray-400">
                        <div>{formatDateTime(item.createdAt)}</div>
                        <div className="mt-1 text-xs text-gray-600">更新: {formatDateTime(item.updatedAt)}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-2">
                          <span className={`inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium ${processingBadgeClass(item.processingStatus)}`}>
                            {item.processingStatus}
                          </span>
                          <span className={`inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(item.repairStatus)}`}>
                            repair: {item.repairStatus}
                          </span>
                        </div>
                        {item.processedAt && (
                          <div className="mt-2 text-xs text-gray-500">
                            处理完成: {formatDateTime(item.processedAt)}
                          </div>
                        )}
                        <div className="mt-2 text-xs text-gray-400">
                          置信度: {typeof item.repairConfidence === "number" ? item.repairConfidence.toFixed(2) : "-"}
                        </div>
                        {latestJob && (
                          <div className="mt-1 text-xs text-gray-500">
                            job: {latestJob.status} / attempt {latestJob.attempt}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="max-w-xs break-all font-medium text-white">{item.audioFilename || "-"}</div>
                        <div className="mt-1 text-gray-400">{item.audioPersonTag || "-"}</div>
                        <div className="mt-1 text-xs text-gray-500">{item.audioDate || "-"}</div>
                        <div className="mt-1 text-xs text-gray-600">
                          {item.audioStartTime || "--"} - {item.audioEndTime || "--"}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-xs text-gray-500">{item.subtitleFile}</div>
                        <div className="mt-1 text-xs text-gray-400">
                          第 {typeof item.subtitleIndex === "number" ? item.subtitleIndex + 1 : "-"} 句 / {formatSubtitleRange(item.subtitleStart, item.subtitleEnd)}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          source: {item.subtitleSourceKind || "-"}#{typeof item.subtitleSourceIndex === "number" ? item.subtitleSourceIndex : "-"}
                        </div>
                        <div className="mt-2 max-w-md whitespace-pre-wrap text-gray-200">{item.subtitleText || "-"}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="max-w-md whitespace-pre-wrap text-gray-100">反馈：{item.message}</div>
                        {item.repairSummary && (
                          <div className="mt-3 max-w-md whitespace-pre-wrap text-sm text-blue-200">AI：{item.repairSummary}</div>
                        )}
                        {item.repairedText && (
                          <div className="mt-2 max-w-md whitespace-pre-wrap rounded-lg bg-gray-800 p-3 text-sm text-green-200">
                            修复后：{item.repairedText}
                          </div>
                        )}
                        {patchJson && (
                          <details className="mt-2 max-w-md rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">
                            <summary className="cursor-pointer text-gray-200">结构化 patch</summary>
                            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{patchJson}</pre>
                          </details>
                        )}
                        {item.repairError && (
                          <div className="mt-2 max-w-md whitespace-pre-wrap text-sm text-red-300">错误：{item.repairError}</div>
                        )}
                        {item.repairedAt && (
                          <div className="mt-2 text-xs text-gray-500">修复时间：{formatDateTime(item.repairedAt)}</div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
