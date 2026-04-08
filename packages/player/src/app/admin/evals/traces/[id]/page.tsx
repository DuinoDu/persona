import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import { AdminNav } from "@/components/AdminNav";
import { formatJsonText, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";
import { buildBatchTracePath, loadBatchTraceFromRun, parseBatchTraceViewerId } from "@ququ/agent/evalArtifacts";

export const dynamic = "force-dynamic";

function renderJsonBlock(value: unknown) {
  const text = formatJsonText(typeof value === "string" ? value : JSON.stringify(value));
  return text || "-";
}

function asText(value: unknown) {
  return typeof value === "string" ? value : "";
}

export default async function EvalTracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const parsed = parseBatchTraceViewerId(id);
  if (!parsed) {
    notFound();
  }

  const run = await prisma.evalRun.findUnique({
    where: { id: parsed.runId },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    notFound();
  }

  const trace = await loadBatchTraceFromRun(
    {
      outputDir: run.outputDir,
      inferHost: run.inferHost
        ? {
            sshHost: run.inferHost.sshHost,
            sshPort: run.inferHost.sshPort,
            sshUser: run.inferHost.sshUser,
            workspacePath: run.inferHost.workspacePath,
          }
        : null,
    },
    parsed.caseId
  );

  if (!trace) {
    notFound();
  }

  const tracePath = run.outputDir ? buildBatchTracePath(run.outputDir, parsed.caseId) : null;
  const messages = Array.isArray(trace.request?.messages) ? trace.request.messages : [];
  const generation = trace.request?.generation || null;
  const rawOutputText = asText(trace.response?.raw_output_text);
  const cleanOutputText = asText(trace.response?.clean_output_text);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="mx-auto max-w-6xl p-6 space-y-6">
        <header className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-400">Trace Viewer</div>
              <h1 className="text-2xl font-bold">{trace.case_id}</h1>
              <p className="mt-1 text-sm text-gray-400">
                run: {run.title} / slice: {trace.slice || "unspecified"}
              </p>
            </div>
            <AdminNav current="/admin/evals" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href={`/admin/evals/runs/${run.id}`} className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition">
              返回 Run 详情
            </Link>
            <span className={`inline-flex rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClass(run.status)}`}>{run.status}</span>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Case</div>
            <div className="mt-2 text-lg font-semibold text-white">{trace.case_id}</div>
            <div className="mt-1 text-xs text-gray-500">{trace.slice || "unspecified"}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Run</div>
            <div className="mt-2 text-lg font-semibold text-white">{run.title}</div>
            <div className="mt-1 text-xs text-gray-500">{run.id}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Deployment</div>
            <div className="mt-2 text-lg font-semibold text-white">{run.modelDeployment?.name || "-"}</div>
            <div className="mt-1 text-xs text-gray-500">{run.modelDeployment?.slug || "-"}</div>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="text-sm text-gray-400">Trace Path</div>
            <div className="mt-2 text-xs text-gray-300">{shortenPath(tracePath, 96)}</div>
            <div className="mt-1 text-xs text-gray-500">{trace.kind}</div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Runtime Signature</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{renderJsonBlock(trace.runtime_signature)}</pre>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Generation</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{renderJsonBlock(generation)}</pre>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <h2 className="text-lg font-semibold text-white">Messages</h2>
            <div className="space-y-3">
              {messages.length === 0 ? (
                <div className="text-sm text-gray-500">暂无 messages</div>
              ) : (
                messages.map((message: Record<string, unknown>, index: number) => {
                  const role = typeof message.role === "string" ? message.role : "unknown";
                  const content = typeof message.content === "string" ? message.content : "";
                  return (
                    <div key={`${role}-${index}`} className="rounded-lg border border-gray-800 bg-gray-950/70 p-3">
                      <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">{role}</div>
                      <div className="whitespace-pre-wrap text-sm text-gray-100">{content || "-"}</div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <h2 className="text-lg font-semibold text-white">Response</h2>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg bg-gray-950/70 p-3">
                <div className="text-xs text-gray-500">raw_output_text</div>
                <div className="mt-2 whitespace-pre-wrap text-sm text-gray-100">{rawOutputText || "-"}</div>
              </div>
              <div className="rounded-lg bg-gray-950/70 p-3">
                <div className="text-xs text-gray-500">clean_output_text</div>
                <div className="mt-2 whitespace-pre-wrap text-sm text-gray-100">{cleanOutputText || "-"}</div>
              </div>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{renderJsonBlock(trace.response)}</pre>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Metrics</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{renderJsonBlock(trace.metrics)}</pre>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
            <h2 className="text-lg font-semibold text-white">Artifacts</h2>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-gray-950/70 p-3 text-xs text-gray-300">{renderJsonBlock(trace.artifacts)}</pre>
          </div>
        </section>
      </div>
    </div>
  );
}
