"use client";

import { useEffect, useState } from "react";

type SourceType = "offline_case" | "live_turn" | "arena_pair";

interface BadCaseQuickCreateProps {
  sourceType: SourceType;
  triggerLabel?: string;
  title?: string;
  defaultSeverity?: string;
  defaultNotes?: string;
  defaultFailureTags?: string;
  defaultEditedTargetText?: string;
  defaultChosenText?: string;
  defaultRejectedText?: string;
  defaultEvalRunId?: string | null;
  defaultCaseId?: string | null;
  defaultLiveTurnId?: string | null;
  defaultSourceId?: string | null;
  onCreated?: (badCase: unknown) => void;
}

interface FormState {
  title: string;
  severity: string;
  failureTags: string;
  notes: string;
  editedTargetText: string;
  chosenText: string;
  rejectedText: string;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function buildInitialState(props: BadCaseQuickCreateProps): FormState {
  return {
    title: props.title || "",
    severity: props.defaultSeverity || "medium",
    failureTags: props.defaultFailureTags || "",
    notes: props.defaultNotes || "",
    editedTargetText: props.defaultEditedTargetText || "",
    chosenText: props.defaultChosenText || "",
    rejectedText: props.defaultRejectedText || "",
  };
}

function splitFailureTags(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function BadCaseQuickCreate(props: BadCaseQuickCreateProps) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(() => buildInitialState(props));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!open) {
      setForm(buildInitialState(props));
      setError("");
      setNotice("");
    }
  }, [open, props]);

  async function submit() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        sourceType: props.sourceType,
        sourceId: props.defaultSourceId || props.defaultCaseId || props.defaultLiveTurnId || null,
        evalRunId: props.defaultEvalRunId || null,
        caseId: props.defaultCaseId || null,
        liveTurnId: props.defaultLiveTurnId || null,
        title: form.title.trim() || null,
        severity: form.severity.trim() || "medium",
        failureTags: splitFailureTags(form.failureTags),
        notes: form.notes.trim() || null,
        editedTargetText: form.editedTargetText.trim() || null,
        chosenText: form.chosenText.trim() || null,
        rejectedText: form.rejectedText.trim() || null,
      };

      const response = await fetch("/api/evals/bad-cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(asString(data?.error) || "创建 bad case 失败");
      }

      setNotice("已标记为 bad case");
      setOpen(false);
      setForm(buildInitialState(props));
      props.onCreated?.(data?.badCase ?? data);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-rose-600/90 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500 transition"
      >
        {props.triggerLabel || "标为 bad case"}
      </button>

      {notice.length > 0 ? <span className="ml-2 text-xs text-emerald-300">{notice}</span> : null}

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-6">
          <div className="w-full max-w-2xl rounded-2xl border border-gray-700 bg-gray-950 p-5 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm text-gray-400">Bad Case</div>
                <h3 className="text-lg font-semibold text-white">{props.title || "标记坏例"}</h3>
                <div className="mt-1 text-xs text-gray-500">{props.sourceType}</div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md bg-gray-800 px-3 py-2 text-xs text-gray-200 hover:bg-gray-700 transition"
              >
                关闭
              </button>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="space-y-2 text-sm text-gray-300">
                <div className="text-xs uppercase tracking-wide text-gray-500">Title</div>
                <input
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                  className="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                  placeholder="可选"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-300">
                <div className="text-xs uppercase tracking-wide text-gray-500">Severity</div>
                <select
                  value={form.severity}
                  onChange={(event) => setForm((current) => ({ ...current, severity: event.target.value }))}
                  className="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="critical">critical</option>
                </select>
              </label>
            </div>

            <label className="mt-3 block space-y-2 text-sm text-gray-300">
              <div className="text-xs uppercase tracking-wide text-gray-500">Failure Tags</div>
              <input
                value={form.failureTags}
                onChange={(event) => setForm((current) => ({ ...current, failureTags: event.target.value }))}
                className="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                placeholder="style_drift, vague_comfort"
              />
            </label>

            <label className="mt-3 block space-y-2 text-sm text-gray-300">
              <div className="text-xs uppercase tracking-wide text-gray-500">Notes</div>
              <textarea
                value={form.notes}
                onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                className="min-h-24 w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                placeholder="简短说明问题"
              />
            </label>

            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <label className="space-y-2 text-sm text-gray-300">
                <div className="text-xs uppercase tracking-wide text-gray-500">Edited Target</div>
                <textarea
                  value={form.editedTargetText}
                  onChange={(event) => setForm((current) => ({ ...current, editedTargetText: event.target.value }))}
                  className="min-h-28 w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                  placeholder="可选"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-300">
                <div className="text-xs uppercase tracking-wide text-gray-500">Chosen</div>
                <textarea
                  value={form.chosenText}
                  onChange={(event) => setForm((current) => ({ ...current, chosenText: event.target.value }))}
                  className="min-h-28 w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                  placeholder="可选"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-300">
                <div className="text-xs uppercase tracking-wide text-gray-500">Rejected</div>
                <textarea
                  value={form.rejectedText}
                  onChange={(event) => setForm((current) => ({ ...current, rejectedText: event.target.value }))}
                  className="min-h-28 w-full rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
                  placeholder="可选"
                />
              </label>
            </div>

            {error.length > 0 ? (
              <div className="mt-4 rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200">{error}</div>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={busy}
                className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {busy ? "提交中..." : "保存 bad case"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
