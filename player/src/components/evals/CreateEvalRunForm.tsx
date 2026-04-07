"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

interface Option {
  id: string;
  label: string;
}

interface Props {
  hosts: Option[];
  deployments: Option[];
  suites: Option[];
}

export function CreateEvalRunForm({ hosts, deployments, suites }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState("");

  const disabled = hosts.length === 0 || deployments.length === 0 || suites.length === 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    setError("");
    startTransition(async () => {
      try {
        const response = await fetch("/api/evals/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data?.error || "创建 run 失败");
        }
        router.push(`/admin/evals/runs/${data.id}`);
      } catch (submitError) {
        setError(submitError instanceof Error ? submitError.message : String(submitError));
      }
    });
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-gray-800 bg-gray-900 p-6 space-y-4">
      <div>
        <div className="text-sm text-gray-400">离线批量评测</div>
        <h2 className="text-xl font-semibold text-white">创建 Eval Run</h2>
      </div>
      <input name="title" placeholder="可留空，系统会自动生成标题" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
      <div className="grid gap-4 md:grid-cols-3">
        <select name="inferHostId" defaultValue={hosts[0]?.id ?? ""} className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required>
          {hosts.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
        <select name="modelDeploymentId" defaultValue={deployments[0]?.id ?? ""} className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required>
          {deployments.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
        <select name="evalSuiteId" defaultValue={suites[0]?.id ?? ""} className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required>
          {suites.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <input name="maxNewTokens" defaultValue="256" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
        <input name="device" defaultValue="cuda" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
        <select name="doSample" defaultValue="false" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
          <option value="false">greedy</option>
          <option value="true">sample</option>
        </select>
        <input name="temperature" defaultValue="0.7" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
      </div>
      <input name="topP" defaultValue="0.95" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
      <input name="systemPromptFile" placeholder="可选：覆盖 deployment 里的 system prompt file" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
      <label className="flex items-center gap-2 text-sm text-gray-300">
        <input name="autoLaunch" type="checkbox" defaultChecked className="h-4 w-4" />
        创建后立刻通过 SSH + tmux 启动远程离线评测
      </label>
      {disabled && <div className="rounded-lg bg-amber-600/20 px-4 py-3 text-sm text-amber-100">先配置 Host、Deployment、Suite。</div>}
      {error && <div className="rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200">{error}</div>}
      <button disabled={pending || disabled} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
        创建 Run
      </button>
    </form>
  );
}
