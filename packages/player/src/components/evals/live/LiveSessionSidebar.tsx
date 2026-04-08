"use client";

import type { FormEvent } from "react";
import { formatDateTime, statusBadgeClass } from "@/lib/evalAdmin";
import type { LiveSessionItem } from "./types";

interface Props {
  selectedDeploymentId: string;
  selectedSessionId: string;
  sessionTitle: string;
  scenario: string;
  busyKey: string;
  filteredSessions: LiveSessionItem[];
  onCreateSession: (event: FormEvent<HTMLFormElement>) => void;
  onSessionTitleChange: (value: string) => void;
  onScenarioChange: (value: string) => void;
  onSelectSession: (sessionId: string) => void;
}

export function LiveSessionSidebar(props: Props) {
  const {
    selectedDeploymentId,
    selectedSessionId,
    sessionTitle,
    scenario,
    busyKey,
    filteredSessions,
    onCreateSession,
    onSessionTitleChange,
    onScenarioChange,
    onSelectSession,
  } = props;

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Live Session</h2>
        <p className="mt-1 text-sm text-gray-400">会话元数据会写入数据库，支持保留多轮 transcript。</p>
      </div>

      <form onSubmit={onCreateSession} className="space-y-3">
        <input
          value={sessionTitle}
          onChange={(event) => onSessionTitleChange(event.target.value)}
          placeholder="会话标题，可留空自动生成"
          className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        />
        <textarea
          value={scenario}
          onChange={(event) => onScenarioChange(event.target.value)}
          placeholder="场景说明，例如婚恋推进 / 连麦试聊"
          className="min-h-24 w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
        />
        <button
          disabled={busyKey.length > 0 || selectedDeploymentId.length === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          新建会话
        </button>
      </form>

      <div className="space-y-3">
        <div className="text-sm font-medium text-gray-200">最近会话</div>
        {filteredSessions.length === 0 ? (
          <div className="rounded-lg bg-gray-950 px-4 py-3 text-sm text-gray-400">
            当前 deployment 还没有 live session。
          </div>
        ) : (
          filteredSessions.map((session) => {
            const active = session.id === selectedSessionId;
            const itemClass = [
              "w-full rounded-lg border px-4 py-3 text-left",
              active
                ? "border-blue-500 bg-blue-500/10"
                : "border-gray-800 bg-gray-950 hover:border-gray-700",
            ].join(" ");
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelectSession(session.id)}
                className={itemClass}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <div className="font-medium text-white">{session.title}</div>
                  <span
                    className={[
                      "inline-flex rounded-full px-2 py-1 text-xs font-medium",
                      statusBadgeClass(session.status),
                    ].join(" ")}
                  >
                    {session.status}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {session.modelDeploymentName || "-"} @ {session.inferHostName || "-"}
                </div>
                <div className="mt-2 text-xs text-gray-400">{formatDateTime(session.updatedAt)}</div>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
