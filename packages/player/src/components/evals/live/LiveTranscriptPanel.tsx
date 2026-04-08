"use client";

import type { FormEvent } from "react";
import { formatDateTime, statusBadgeClass } from "@/lib/evalAdmin";
import { BadCaseQuickCreate } from "@/components/evals/BadCaseQuickCreate";
import type { LiveSessionItem } from "./types";

interface Props {
  deploymentsCount: number;
  selectedSession: LiveSessionItem | null;
  selectedDeploymentIsStarting: boolean;
  streamingSessionId: string;
  streamingAssistantText: string;
  streamingUserText: string;
  streamingLatencyMs: number | null;
  streamingTokenCount: number | null;
  messageInput: string;
  maxNewTokens: string;
  temperature: string;
  topP: string;
  doSample: boolean;
  busyKey: string;
  onSendMessage: (event: FormEvent<HTMLFormElement>) => void;
  onMessageInputChange: (value: string) => void;
  onMaxNewTokensChange: (value: string) => void;
  onTemperatureChange: (value: string) => void;
  onTopPChange: (value: string) => void;
  onDoSampleChange: (value: boolean) => void;
}

export function LiveTranscriptPanel(props: Props) {
  const {
    deploymentsCount,
    selectedSession,
    selectedDeploymentIsStarting,
    streamingSessionId,
    streamingAssistantText,
    streamingUserText,
    streamingLatencyMs,
    streamingTokenCount,
    messageInput,
    maxNewTokens,
    temperature,
    topP,
    doSample,
    busyKey,
    onSendMessage,
    onMessageInputChange,
    onMaxNewTokensChange,
    onTemperatureChange,
    onTopPChange,
    onDoSampleChange,
  } = props;

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Transcript</h2>
        <p className="mt-1 text-sm text-gray-400">本地 web 通过 SSH 代理 H20 上的常驻推理服务，当前支持流式输出。</p>
      </div>

      {selectedDeploymentIsStarting ? (
        <div className="rounded-lg bg-amber-500/15 px-4 py-3 text-sm text-amber-100">
          服务正在 H20 上冷启动加载模型，通常需要 3 到 5 分钟。页面会自动轮询状态；现在直接发送也可以，后端会先等待
          service ready 再开始推理。
        </div>
      ) : null}

      {selectedSession ? (
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium text-white">{selectedSession.title}</div>
              <div className="mt-1 text-xs text-gray-500">
                {selectedSession.modelDeploymentName || "-"} @ {selectedSession.inferHostName || "-"}
              </div>
            </div>
            <span
              className={[
                "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                statusBadgeClass(selectedSession.status),
              ].join(" ")}
            >
              {selectedSession.status}
            </span>
          </div>
          {selectedSession.scenario ? (
            <div className="rounded bg-gray-900 px-3 py-2 text-sm text-gray-300">
              场景：{selectedSession.scenario}
            </div>
          ) : null}
          {selectedSession.notes ? (
            <div className="rounded bg-red-600/15 px-3 py-2 text-sm text-red-100 whitespace-pre-wrap break-words">
              {selectedSession.notes}
            </div>
          ) : null}
          <div className="max-h-[480px] space-y-3 overflow-y-auto pr-1">
            {selectedSession.turns.length === 0 && !(streamingSessionId === selectedSession.id && streamingUserText) ? (
              <div className="rounded bg-gray-900 px-3 py-3 text-sm text-gray-400">
                还没有消息，直接在下面发送第一条问题。
              </div>
            ) : (
              <>
                {selectedSession.turns.map((turn) => {
                  const turnClass =
                    turn.role === "assistant"
                      ? "rounded-lg px-4 py-3 text-sm bg-blue-500/10 text-blue-50"
                      : "rounded-lg px-4 py-3 text-sm bg-gray-900 text-gray-200";
                  return (
                    <div key={turn.id} className={turnClass}>
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs uppercase tracking-wide text-gray-400">
                        <div className="flex flex-wrap items-center gap-3">
                          <span>{turn.role}</span>
                          {turn.latencyMs ? <span>{turn.latencyMs} ms</span> : null}
                          {turn.tokenCount ? <span>{turn.tokenCount} tokens</span> : null}
                          <span>{formatDateTime(turn.createdAt)}</span>
                        </div>
                        {turn.role === "assistant" ? (
                          <BadCaseQuickCreate
                            sourceType="live_turn"
                            triggerLabel="标坏例"
                            title={`${selectedSession.title} / assistant`}
                            defaultLiveTurnId={turn.id}
                            defaultSourceId={turn.id}
                            defaultSeverity="medium"
                            defaultNotes={`${selectedSession.title} / ${turn.createdAt}`}
                          />
                        ) : null}
                      </div>
                      <div className="whitespace-pre-wrap break-words">{turn.content}</div>
                    </div>
                  );
                })}
                {streamingSessionId === selectedSession.id && streamingUserText ? (
                  <div className="rounded-lg px-4 py-3 text-sm bg-gray-900 text-gray-200">
                    <div className="mb-2 flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-gray-400">
                      <span>user</span>
                      <span>just now</span>
                    </div>
                    <div className="whitespace-pre-wrap break-words">{streamingUserText}</div>
                  </div>
                ) : null}
                {streamingSessionId === selectedSession.id ? (
                  <div className="rounded-lg px-4 py-3 text-sm bg-blue-500/10 text-blue-50">
                    <div className="mb-2 flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-gray-400">
                      <span>assistant</span>
                      <span>streaming</span>
                      {streamingLatencyMs ? <span>{streamingLatencyMs} ms</span> : null}
                      {streamingTokenCount ? <span>{streamingTokenCount} tokens</span> : null}
                    </div>
                    <div className="whitespace-pre-wrap break-words">
                      {streamingAssistantText || "正在生成..."}
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-gray-700 bg-gray-950 px-4 py-10 text-sm text-gray-400">
          先创建一个会话，或者从左侧选择已有会话。
        </div>
      )}

      <form onSubmit={onSendMessage} className="space-y-3">
        <textarea
          value={messageInput}
          onChange={(event) => onMessageInputChange(event.target.value)}
          placeholder="输入你要模拟连麦发送的问题"
          className="min-h-32 w-full rounded-lg bg-gray-800 px-3 py-3 text-sm text-white"
        />
        <div className="grid gap-3 md:grid-cols-4">
          <input
            value={maxNewTokens}
            onChange={(event) => onMaxNewTokensChange(event.target.value)}
            className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
          />
          <select
            value={doSample ? "true" : "false"}
            onChange={(event) => onDoSampleChange(event.target.value === "true")}
            className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
          >
            <option value="false">greedy</option>
            <option value="true">sample</option>
          </select>
          <input
            value={temperature}
            onChange={(event) => onTemperatureChange(event.target.value)}
            className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
          />
          <input
            value={topP}
            onChange={(event) => onTopPChange(event.target.value)}
            className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
          />
        </div>
        <button
          disabled={busyKey.length > 0 || deploymentsCount === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {busyKey === "send-message" ? "发送中..." : "发送消息"}
        </button>
      </form>
    </section>
  );
}
