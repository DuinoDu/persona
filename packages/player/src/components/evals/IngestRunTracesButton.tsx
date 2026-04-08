"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type IngestStatus = "idle" | "running" | "success" | "error";

interface IngestResult {
  runId?: string;
  totalCases?: number;
  imported?: number;
  updated?: number;
  skipped?: number;
  missingTraceArtifacts?: number;
  force?: boolean;
}

function statusClass(status: IngestStatus) {
  switch (status) {
    case "running":
      return "bg-sky-600/20 text-sky-300";
    case "success":
      return "bg-emerald-600/20 text-emerald-300";
    case "error":
      return "bg-red-600/20 text-red-300";
    default:
      return "bg-gray-700/40 text-gray-300";
  }
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

export function IngestRunTracesButton({ runId }: { runId: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<IngestStatus>("idle");
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState("");

  async function handleIngest() {
    setStatus("running");
    setError("");

    try {
      const response = await fetch(`/api/evals/runs/${runId}/ingest-traces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(asString(data?.error) || "ingest traces 失败");
      }

      setResult(data as IngestResult);
      setStatus("success");
      router.refresh();
    } catch (submitError) {
      setResult(null);
      setStatus("error");
      setError(submitError instanceof Error ? submitError.message : String(submitError));
    }
  }

  const hasCounts = result !== null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm text-gray-400">Offline Trace Ingest</div>
          <h2 className="text-lg font-semibold text-white">一键导入 Run Traces</h2>
          <p className="mt-1 text-sm text-gray-400">从当前 run 的 generations / traces 里抓取 offline traces 并写入 inference_trace。</p>
        </div>
        <button
          type="button"
          onClick={() => void handleIngest()}
          disabled={status === "running"}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition disabled:cursor-not-allowed disabled:opacity-60"
        >
          {status === "running" ? "导入中..." : "Ingest Offline Traces"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${statusClass(status)}`}>
          {status === "running" ? "running" : status}
        </span>
        {hasCounts ? (
          <>
            <span className="inline-flex rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-200">imported: {result.imported ?? 0}</span>
            <span className="inline-flex rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-200">updated: {result.updated ?? 0}</span>
            <span className="inline-flex rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-200">skipped: {result.skipped ?? 0}</span>
            <span className="inline-flex rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-200">
              missingTraceArtifacts: {result.missingTraceArtifacts ?? 0}
            </span>
            {typeof result.totalCases === "number" ? (
              <span className="inline-flex rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-200">totalCases: {result.totalCases}</span>
            ) : null}
          </>
        ) : null}
      </div>

      {error ? <div className="rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200">{error}</div> : null}
    </div>
  );
}
