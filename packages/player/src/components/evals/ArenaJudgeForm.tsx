"use client";

import { FormEvent, useMemo, useState } from "react";
import { formatDateTime } from "@/lib/evalAdmin";

const SCORE_FIELDS = [
  { key: "personaScore", label: "Persona" },
  { key: "judgmentScore", label: "Judgment" },
  { key: "premiseScore", label: "Premise" },
  { key: "structureScore", label: "Structure" },
  { key: "actionabilityScore", label: "Actionability" },
  { key: "naturalnessScore", label: "Naturalness" },
  { key: "stabilityScore", label: "Stability" },
] as const;

const FAILURE_TAGS = [
  "too_short",
  "style_drift",
  "no_premise_fix",
  "vague_comfort",
  "too_harsh",
  "multi_turn_drift",
  "leakage",
] as const;

type ScoreKey = (typeof SCORE_FIELDS)[number]["key"];

interface ExistingJudgment {
  winner: string;
  winnerEvalRunId: string | null;
  personaScore: number | null;
  judgmentScore: number | null;
  premiseScore: number | null;
  structureScore: number | null;
  actionabilityScore: number | null;
  naturalnessScore: number | null;
  stabilityScore: number | null;
  failureTags: string[];
  notes: string | null;
  updatedAt: string;
}

interface Props {
  evalSuiteId: string | null;
  leftEvalRunId: string;
  rightEvalRunId: string;
  caseId: string;
  caseSlice: string;
  promptPreview: string;
  existingJudgment: ExistingJudgment | null;
}

function asScoreText(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

export function ArenaJudgeForm(props: Props) {
  const [winner, setWinner] = useState(props.existingJudgment?.winner || "skip");
  const [scores, setScores] = useState<Record<ScoreKey, string>>({
    personaScore: asScoreText(props.existingJudgment?.personaScore),
    judgmentScore: asScoreText(props.existingJudgment?.judgmentScore),
    premiseScore: asScoreText(props.existingJudgment?.premiseScore),
    structureScore: asScoreText(props.existingJudgment?.structureScore),
    actionabilityScore: asScoreText(props.existingJudgment?.actionabilityScore),
    naturalnessScore: asScoreText(props.existingJudgment?.naturalnessScore),
    stabilityScore: asScoreText(props.existingJudgment?.stabilityScore),
  });
  const [failureTags, setFailureTags] = useState<string[]>(props.existingJudgment?.failureTags || []);
  const [notes, setNotes] = useState(props.existingJudgment?.notes || "");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<string | null>(props.existingJudgment?.updatedAt || null);

  const selectedTags = useMemo(() => new Set(failureTags), [failureTags]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const payload: Record<string, unknown> = {
        evalSuiteId: props.evalSuiteId,
        leftEvalRunId: props.leftEvalRunId,
        rightEvalRunId: props.rightEvalRunId,
        caseId: props.caseId,
        caseSlice: props.caseSlice,
        promptPreview: props.promptPreview,
        winner,
        failureTags,
        notes: notes.trim(),
      };
      for (const field of SCORE_FIELDS) {
        payload[field.key] = scores[field.key].trim();
      }

      const response = await fetch("/api/evals/arena/judgments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok === false) {
        throw new Error(typeof data.error === "string" ? data.error : "保存失败");
      }

      setSavedAt(typeof data?.judgment?.updatedAt === "string" ? data.judgment.updatedAt : new Date().toISOString());
      setNotice("已保存盲评结果");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : String(submitError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5 rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Blind Arena Judgment</h2>
          <p className="mt-1 text-sm text-gray-400">只看 A / B 输出，不在这里暴露对应模型。</p>
        </div>
        {savedAt ? <div className="text-xs text-gray-500">最近保存：{formatDateTime(savedAt)}</div> : null}
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        {[
          { value: "A", label: "A 更好" },
          { value: "B", label: "B 更好" },
          { value: "tie", label: "平局" },
          { value: "skip", label: "跳过" },
        ].map((item) => {
          const active = winner === item.value;
          return (
            <label
              key={item.value}
              className={[
                "cursor-pointer rounded-lg border px-4 py-3 text-sm transition",
                active ? "border-blue-500 bg-blue-500/10 text-blue-100" : "border-gray-800 bg-gray-950 text-gray-300",
              ].join(" ")}
            >
              <input
                type="radio"
                name="winner"
                value={item.value}
                checked={active}
                onChange={(event) => setWinner(event.target.value)}
                className="sr-only"
              />
              {item.label}
            </label>
          );
        })}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {SCORE_FIELDS.map((field) => (
          <label key={field.key} className="space-y-2">
            <div className="text-sm text-gray-300">{field.label}</div>
            <select
              value={scores[field.key]}
              onChange={(event) =>
                setScores((current) => ({
                  ...current,
                  [field.key]: event.target.value,
                }))
              }
              className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
            >
              <option value="">未打分</option>
              {[1, 2, 3, 4, 5].map((score) => (
                <option key={score} value={String(score)}>
                  {score}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div className="space-y-3">
        <div className="text-sm font-medium text-gray-200">失败标签</div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {FAILURE_TAGS.map((tag) => {
            const active = selectedTags.has(tag);
            return (
              <label
                key={tag}
                className={[
                  "cursor-pointer rounded-lg border px-3 py-2 text-sm transition",
                  active ? "border-amber-500 bg-amber-500/10 text-amber-100" : "border-gray-800 bg-gray-950 text-gray-300",
                ].join(" ")}
              >
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(event) => {
                    if (event.target.checked) {
                      setFailureTags((items) => items.concat(tag).filter((value, index, list) => list.indexOf(value) === index));
                    } else {
                      setFailureTags((items) => items.filter((value) => value !== tag));
                    }
                  }}
                  className="sr-only"
                />
                {tag}
              </label>
            );
          })}
        </div>
      </div>

      <label className="block space-y-2">
        <div className="text-sm text-gray-300">备注</div>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="记录为什么选 A/B，或者这条 case 的主要问题。"
          className="min-h-28 w-full rounded-lg bg-gray-800 px-3 py-3 text-sm text-white"
        />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busy ? "保存中..." : "保存评判"}
        </button>
        {notice ? <div className="text-sm text-emerald-300">{notice}</div> : null}
        {error ? <div className="text-sm text-red-300">{error}</div> : null}
      </div>
    </form>
  );
}
