"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDateTime, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";

export interface BadCaseExportItem {
  id: string;
  status: string;
  severity: string;
  title: string;
  sourceType: string;
  sourceId: string | null;
  caseId: string | null;
  failureTags: string[];
  notes: string | null;
  modelDeploymentSlug: string | null;
  evalRunId: string | null;
  evalRunTitle: string | null;
  liveSessionTitle: string | null;
  liveSessionId: string | null;
  traceHref: string | null;
  createdAt: string;
  updatedAt: string;
}

interface Props {
  items: BadCaseExportItem[];
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

export function BadCaseExportPanel({ items }: Props) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [recordKind, setRecordKind] = useState("auto");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [annotatorId, setAnnotatorId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [createdExportId, setCreatedExportId] = useState("");

  const selectedCount = selectedIds.length;
  const allSelected = items.length > 0 && selectedCount === items.length;

  const selectedSummary = useMemo(() => {
    if (selectedIds.length === 0) {
      return "未选择坏例";
    }
    return `已选择 ${selectedIds.length} 条坏例`;
  }, [selectedIds.length]);

  function toggleItem(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : current.concat(id)
    );
  }

  function toggleAll() {
    setSelectedIds((current) => (current.length === items.length ? [] : items.map((item) => item.id)));
  }

  async function createExport() {
    if (selectedIds.length === 0) {
      setError("请先选择至少一个 bad case");
      return;
    }

    setBusy(true);
    setError("");
    setNotice("");
    setCreatedExportId("");
    try {
      const response = await fetch("/api/evals/exports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          badCaseIds: selectedIds,
          recordKind,
          title: title.trim() || null,
          notes: notes.trim() || null,
          annotatorId: annotatorId.trim() || null,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(asString(data?.error) || "创建导出失败");
      }
      const exportId = asString(data?.export?.id);
      setCreatedExportId(exportId);
      setNotice(`导出已创建，共 ${selectedIds.length} 条`);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">批量导出</h2>
          <p className="mt-1 text-sm text-gray-400">从当前 bad cases 列表勾选样本，直接生成训练导出。</p>
        </div>
        <div className="text-sm text-gray-500">{selectedSummary}</div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <select
          value={recordKind}
          onChange={(event) => setRecordKind(event.target.value)}
          className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        >
          <option value="auto">auto</option>
          <option value="sft_candidate">sft_candidate</option>
          <option value="preference_pair_candidate">preference_pair_candidate</option>
        </select>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="导出标题（可选）"
          className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        />
        <input
          value={annotatorId}
          onChange={(event) => setAnnotatorId(event.target.value)}
          placeholder="annotatorId（可选）"
          className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        />
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="notes（可选）"
          className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={toggleAll}
          className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
        >
          {allSelected ? "取消全选" : "全选当前页"}
        </button>
        <button
          type="button"
          onClick={() => setSelectedIds([])}
          className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
        >
          清空选择
        </button>
        <button
          type="button"
          onClick={() => void createExport()}
          disabled={busy || selectedIds.length === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "导出中..." : "生成导出"}
        </button>
        <Link href="/admin/evals/exports" className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
          查看导出列表
        </Link>
      </div>

      {error ? <div className="rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200">{error}</div> : null}
      {notice ? (
        <div className="rounded-lg bg-emerald-600/20 px-4 py-3 text-sm text-emerald-200">
          {notice}
          {createdExportId ? (
            <span className="ml-2">
              <Link href="/admin/evals/exports" className="underline">
                打开 exports
              </Link>
              <span className="mx-1">/</span>
              <a href={`/api/evals/exports/${createdExportId}/download`} className="underline">
                下载 JSONL
              </a>
            </span>
          ) : null}
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-sm text-gray-400">
          暂无坏例
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-gray-400">
              <tr>
                <th className="px-3 py-2 font-medium">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>
                <th className="px-3 py-2 font-medium">状态</th>
                <th className="px-3 py-2 font-medium">来源</th>
                <th className="px-3 py-2 font-medium">Tags</th>
                <th className="px-3 py-2 font-medium">Notes</th>
                <th className="px-3 py-2 font-medium">关联 Run / Session</th>
                <th className="px-3 py-2 font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const sourceText = [
                  item.sourceType,
                  item.sourceId,
                  item.caseId ? `case:${item.caseId}` : null,
                ]
                  .filter(Boolean)
                  .join(" / ");
                const checked = selectedIds.includes(item.id);
                return (
                  <tr key={item.id} className="border-t border-gray-800 align-top">
                    <td className="px-3 py-3">
                      <input type="checkbox" checked={checked} onChange={() => toggleItem(item.id)} />
                    </td>
                    <td className="px-3 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusBadgeClass(item.status)}`}>
                        {item.status}
                      </span>
                      <div className="mt-2 text-xs text-gray-500">{item.severity}</div>
                    </td>
                    <td className="px-3 py-3 text-gray-300">
                      <div className="font-medium text-white">{item.title || item.id}</div>
                      <div className="mt-1 text-xs text-gray-500">{sourceText || "-"}</div>
                      <div className="mt-1 text-xs text-gray-500">{item.modelDeploymentSlug || "-"}</div>
                    </td>
                    <td className="px-3 py-3 text-gray-300">
                      <div className="max-w-xs whitespace-pre-wrap text-xs text-gray-200">
                        {item.failureTags.length > 0 ? item.failureTags.join(", ") : "-"}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-gray-300">
                      <div className="max-w-sm whitespace-pre-wrap text-xs leading-5 text-gray-200">
                        {item.notes || "-"}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-gray-300">
                      {item.evalRunId ? (
                        <Link href={`/admin/evals/runs/${item.evalRunId}`} className="font-medium text-blue-300 hover:text-blue-200">
                          {item.evalRunTitle || item.evalRunId}
                        </Link>
                      ) : (
                        <div>{item.evalRunTitle || "-"}</div>
                      )}
                      <div className="mt-1 text-xs text-gray-500">
                        {item.liveSessionTitle ? `${item.liveSessionTitle} / ${item.liveSessionId}` : "-"}
                      </div>
                      {item.traceHref ? (
                        <div className="mt-2">
                          <Link href={item.traceHref} className="inline-flex rounded-lg bg-gray-800 px-3 py-2 text-xs text-gray-200 hover:bg-gray-700 transition">
                            Open trace
                          </Link>
                        </div>
                      ) : null}
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
  );
}
