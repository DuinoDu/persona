"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

interface HostOption {
  id: string;
  name: string;
}

async function postForm(path: string, form: HTMLFormElement) {
  const payload = Object.fromEntries(new FormData(form).entries());
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.error || "请求失败");
  }
  return data;
}

export function SetupPanel({ hosts }: { hosts: HostOption[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (path: string) => async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    setMessage("");
    setError("");
    startTransition(async () => {
      try {
        await postForm(path, form);
        setMessage(`已提交到 ${path}`);
        form.reset();
        router.refresh();
      } catch (submitError) {
        setError(submitError instanceof Error ? submitError.message : String(submitError));
      }
    });
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-3">
        <form onSubmit={handleSubmit("/api/infer/hosts")} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
          <div>
            <div className="text-sm text-gray-400">新增 Infer Host</div>
            <h3 className="text-lg font-semibold text-white">推理 H20</h3>
          </div>
          <input name="name" placeholder="h20-infer-01" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input name="sshHost" placeholder="115.xxx.xxx.xxx" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <div className="grid grid-cols-2 gap-3">
            <input name="sshPort" placeholder="22" defaultValue="22" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
            <input name="sshUser" placeholder="root" defaultValue="root" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          </div>
          <input
            name="workspacePath"
            defaultValue="/vita-vepfs-data/fileset1/usr_data/yueyu/ws/persona"
            className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
            required
          />
          <select name="gpuPolicy" defaultValue="shared_service" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
            <option value="shared_service">shared_service</option>
            <option value="exclusive_batch">exclusive_batch</option>
            <option value="multi_gpu_split">multi_gpu_split</option>
          </select>
          <textarea name="notes" placeholder="备注" className="min-h-20 w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <button disabled={pending} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            保存 Host
          </button>
        </form>

        <form onSubmit={handleSubmit("/api/infer/deployments")} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
          <div>
            <div className="text-sm text-gray-400">新增 Deployment</div>
            <h3 className="text-lg font-semibold text-white">模型部署</h3>
          </div>
          <select name="inferHostId" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required defaultValue={hosts[0]?.id ?? ""}>
            {hosts.length === 0 ? <option value="">先创建 Host</option> : hosts.map((host) => <option key={host.id} value={host.id}>{host.name}</option>)}
          </select>
          <input name="name" placeholder="qwen35-9b-final" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input name="slug" placeholder="qwen35-9b-final" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input name="baseModelPath" placeholder="base model path" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input name="adapterPath" placeholder="adapter path，可留空表示 base-only" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <input name="systemPromptFile" placeholder="system prompt file" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <input
            name="runnerScriptPath"
            defaultValue="/vita-vepfs-data/fileset1/usr_data/yueyu/ws/persona/scripts/evals/run_batch_chat_eval_py312.sh"
            className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
          />
          <div className="grid grid-cols-2 gap-3">
            <select name="serviceMode" defaultValue="offline_only" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white">
              <option value="offline_only">offline_only</option>
              <option value="shared_service">shared_service</option>
              <option value="dual_mode">dual_mode</option>
            </select>
            <input name="defaultDevice" defaultValue="cuda" className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          </div>
          <textarea name="notes" placeholder="备注" className="min-h-20 w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <button disabled={pending || hosts.length === 0} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            保存 Deployment
          </button>
        </form>

        <form onSubmit={handleSubmit("/api/evals/suites")} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
          <div>
            <div className="text-sm text-gray-400">新增 Eval Suite</div>
            <h3 className="text-lg font-semibold text-white">固定评测集</h3>
          </div>
          <input name="slug" placeholder="persona-baseline-smoke-v1" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input name="title" placeholder="Persona Baseline Smoke V1" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" required />
          <input
            name="sourcePath"
            defaultValue="/vita-vepfs-data/fileset1/usr_data/yueyu/ws/persona/artifacts/evals/suites/persona_baseline_smoke_v1.jsonl"
            className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
            required
          />
          <input name="caseCount" placeholder="留空则自动数 JSONL 行数" className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <textarea name="description" placeholder="suite 描述" className="min-h-20 w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white" />
          <button disabled={pending} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            保存 Suite
          </button>
        </form>
      </div>

      {(message || error) && (
        <div className={`rounded-lg px-4 py-3 text-sm ${error ? "bg-red-600/20 text-red-200" : "bg-emerald-600/20 text-emerald-200"}`}>
          {error || message}
        </div>
      )}
    </div>
  );
}
