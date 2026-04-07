"use client";

import { FormEvent, useEffect, useState } from "react";
import { formatDateTime, formatJsonText, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";

interface DeploymentItem {
  id: string;
  name: string;
  slug: string;
  inferHostName: string;
  inferHostId: string;
  serviceMode: string;
  serviceStatus: string;
  serviceBaseUrl: string | null;
  serviceChatPath: string | null;
  serviceSessionName: string | null;
  serviceLogPath: string | null;
  serviceStatusPath: string | null;
  serviceLastExitCode: number | null;
  serviceLastError: string | null;
  serviceLastHealthJson: string | null;
  serviceLastCheckedAt: string | null;
  notes: string | null;
}

interface LiveTurnItem {
  id: string;
  role: string;
  content: string;
  latencyMs: number | null;
  tokenCount: number | null;
  createdAt: string;
}

interface LiveSessionItem {
  id: string;
  title: string;
  status: string;
  scenario: string | null;
  notes: string | null;
  inferHostId: string | null;
  modelDeploymentId: string | null;
  modelDeploymentName: string | null;
  inferHostName: string | null;
  createdAt: string;
  updatedAt: string;
  turns: LiveTurnItem[];
}

interface ServiceArtifacts {
  sessionName: string;
  logPath: string;
  statusPath: string;
  baseUrl: string;
  healthUrl: string;
  chatUrl: string;
  port: number | null;
  listenHost: string | null;
}

interface ServiceProbe {
  sessionState: string;
  exitCode: number | null;
  healthJson: unknown;
  logTail: string | null;
}

interface ServiceDebugState {
  artifacts: ServiceArtifacts | null;
  probe: ServiceProbe | null;
  updatedAt: string;
}

interface Props {
  deployments: DeploymentItem[];
  initialSessions: LiveSessionItem[];
}

class ApiError extends Error {
  payload: unknown;

  constructor(message: string, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.payload = payload;
  }
}

function asRecord(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNullableNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeDeployment(value: unknown): DeploymentItem {
  const record = asRecord(value) || {};
  const inferHost = asRecord(record.inferHost);
  return {
    id: asString(record.id),
    name: asString(record.name),
    slug: asString(record.slug),
    inferHostName: asString(record.inferHostName) || asString(inferHost?.name) || "-",
    inferHostId: asString(record.inferHostId) || asString(inferHost?.id),
    serviceMode: asString(record.serviceMode) || "offline_only",
    serviceStatus: asString(record.serviceStatus) || "stopped",
    serviceBaseUrl: asNullableString(record.serviceBaseUrl),
    serviceChatPath: asNullableString(record.serviceChatPath),
    serviceSessionName: asNullableString(record.serviceSessionName),
    serviceLogPath: asNullableString(record.serviceLogPath),
    serviceStatusPath: asNullableString(record.serviceStatusPath),
    serviceLastExitCode: asNullableNumber(record.serviceLastExitCode),
    serviceLastError: asNullableString(record.serviceLastError),
    serviceLastHealthJson: asNullableString(record.serviceLastHealthJson),
    serviceLastCheckedAt: asNullableString(record.serviceLastCheckedAt),
    notes: asNullableString(record.notes),
  };
}

function normalizeTurn(value: unknown): LiveTurnItem {
  const record = asRecord(value) || {};
  return {
    id: asString(record.id),
    role: asString(record.role) || "user",
    content: asString(record.content),
    latencyMs: asNullableNumber(record.latencyMs),
    tokenCount: asNullableNumber(record.tokenCount),
    createdAt: asString(record.createdAt),
  };
}

function normalizeSession(value: unknown): LiveSessionItem {
  const record = asRecord(value) || {};
  const inferHost = asRecord(record.inferHost);
  const deployment = asRecord(record.modelDeployment);
  const turnsRaw = Array.isArray(record.turns) ? record.turns : [];
  return {
    id: asString(record.id),
    title: asString(record.title),
    status: asString(record.status) || "draft",
    scenario: asNullableString(record.scenario),
    notes: asNullableString(record.notes),
    inferHostId: asNullableString(record.inferHostId) || asNullableString(inferHost?.id),
    modelDeploymentId: asNullableString(record.modelDeploymentId) || asNullableString(deployment?.id),
    modelDeploymentName: asNullableString(record.modelDeploymentName) || asNullableString(deployment?.name),
    inferHostName: asNullableString(record.inferHostName) || asNullableString(inferHost?.name),
    createdAt: asString(record.createdAt),
    updatedAt: asString(record.updatedAt),
    turns: turnsRaw.map(normalizeTurn),
  };
}

function normalizeServiceArtifacts(value: unknown): ServiceArtifacts | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const sessionName = asString(record.sessionName);
  const logPath = asString(record.logPath);
  const statusPath = asString(record.statusPath);
  const baseUrl = asString(record.baseUrl);
  if (!sessionName && !logPath && !statusPath && !baseUrl) {
    return null;
  }
  return {
    sessionName,
    logPath,
    statusPath,
    baseUrl,
    healthUrl: asString(record.healthUrl),
    chatUrl: asString(record.chatUrl),
    port: asNullableNumber(record.port),
    listenHost: asNullableString(record.listenHost),
  };
}

function normalizeServiceProbe(value: unknown): ServiceProbe | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    sessionState: asString(record.sessionState) || "unknown",
    exitCode: asNullableNumber(record.exitCode),
    healthJson: record.healthJson ?? null,
    logTail: asNullableString(record.logTail),
  };
}

function extractErrorPayload(error: unknown) {
  return error instanceof ApiError ? error.payload : null;
}

async function readJson(response: Response) {
  return response.json().catch(() => ({}));
}

export function LiveInferConsole({ deployments: initialDeployments, initialSessions }: Props) {
  const [deployments, setDeployments] = useState(() => initialDeployments.map(normalizeDeployment));
  const [sessions, setSessions] = useState(() => initialSessions.map(normalizeSession));
  const [selectedDeploymentId, setSelectedDeploymentId] = useState(initialDeployments[0]?.id || "");
  const [selectedSessionId, setSelectedSessionId] = useState(initialSessions[0]?.id || "");
  const [sessionTitle, setSessionTitle] = useState("");
  const [scenario, setScenario] = useState("");
  const [messageInput, setMessageInput] = useState("");
  const [maxNewTokens, setMaxNewTokens] = useState("256");
  const [temperature, setTemperature] = useState("0.7");
  const [topP, setTopP] = useState("0.95");
  const [doSample, setDoSample] = useState(false);
  const [busyKey, setBusyKey] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [serviceDebugByDeploymentId, setServiceDebugByDeploymentId] = useState<Record<string, ServiceDebugState>>({});

  useEffect(() => {
    if (selectedDeploymentId.length === 0 && deployments.length > 0) {
      setSelectedDeploymentId(deployments[0].id);
      return;
    }

    const current = sessions.find((item) => item.id === selectedSessionId);
    if (current && (selectedDeploymentId.length === 0 || current.modelDeploymentId === selectedDeploymentId)) {
      return;
    }

    const next = sessions.find((item) => item.modelDeploymentId === selectedDeploymentId);
    setSelectedSessionId(next ? next.id : "");
  }, [deployments, selectedDeploymentId, selectedSessionId, sessions]);

  const selectedDeployment = deployments.find((item) => item.id === selectedDeploymentId) || null;
  const selectedSession = sessions.find((item) => item.id === selectedSessionId) || null;
  const selectedDebug = selectedDeploymentId ? serviceDebugByDeploymentId[selectedDeploymentId] || null : null;
  const filteredSessions = sessions.filter((item) => {
    if (selectedDeploymentId.length === 0) {
      return true;
    }
    return item.modelDeploymentId === selectedDeploymentId;
  });

  const selectedHealthText = selectedDebug?.probe?.healthJson
    ? formatJsonText(JSON.stringify(selectedDebug.probe.healthJson))
    : formatJsonText(selectedDeployment?.serviceLastHealthJson);

  async function runAction<T>(key: string, action: () => Promise<T>) {
    setBusyKey(key);
    setNotice("");
    setError("");
    try {
      return await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
      throw actionError;
    } finally {
      setBusyKey("");
    }
  }

  function upsertDeployment(value: unknown) {
    const next = normalizeDeployment(value);
    setDeployments((items) => {
      const found = items.some((item) => item.id === next.id);
      if (found === false) {
        return [next].concat(items);
      }
      return items.map((item) => (item.id === next.id ? next : item));
    });
  }

  function upsertSession(value: unknown) {
    const next = normalizeSession(value);
    setSessions((items) => {
      const rest = items.filter((item) => item.id !== next.id);
      return [next].concat(rest);
    });
  }

  function putServiceDebug(deploymentId: string, artifactsValue: unknown, probeValue: unknown) {
    if (deploymentId.length === 0) {
      return;
    }
    setServiceDebugByDeploymentId((items) => ({
      ...items,
      [deploymentId]: {
        artifacts: normalizeServiceArtifacts(artifactsValue) || items[deploymentId]?.artifacts || null,
        probe: normalizeServiceProbe(probeValue) || items[deploymentId]?.probe || null,
        updatedAt: new Date().toISOString(),
      },
    }));
  }

  async function postJson(path: string, payload: unknown) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await readJson(response);
    if (response.ok === false) {
      throw new ApiError(asString(asRecord(data)?.error) || "请求失败", data);
    }
    return data;
  }

  async function getJson(path: string) {
    const response = await fetch(path, { cache: "no-store" });
    const data = await readJson(response);
    if (response.ok === false) {
      throw new ApiError(asString(asRecord(data)?.error) || "请求失败", data);
    }
    return data;
  }

  async function handleStartService(deploymentId: string) {
    try {
      const data = await runAction("start:" + deploymentId, () =>
        postJson("/api/infer/deployments/" + deploymentId + "/service/start", {})
      );
      const record = asRecord(data);
      if (record?.deployment) {
        upsertDeployment(record.deployment);
      }
      putServiceDebug(deploymentId, record?.artifacts || record?.launch, null);
      setNotice("已启动服务：" + normalizeDeployment(record?.deployment).name);
    } catch (actionError) {
      const payload = asRecord(extractErrorPayload(actionError));
      if (payload?.deployment) {
        upsertDeployment(payload.deployment);
      }
      putServiceDebug(deploymentId, payload?.artifacts, payload?.probe);
    }
  }

  async function handleStopService(deploymentId: string) {
    try {
      const data = await runAction("stop:" + deploymentId, () =>
        postJson("/api/infer/deployments/" + deploymentId + "/service/stop", {})
      );
      const record = asRecord(data);
      if (record?.deployment) {
        upsertDeployment(record.deployment);
      }
      putServiceDebug(deploymentId, record?.artifacts, null);
      setNotice("已停止服务：" + normalizeDeployment(record?.deployment).name);
    } catch (actionError) {
      const payload = asRecord(extractErrorPayload(actionError));
      if (payload?.deployment) {
        upsertDeployment(payload.deployment);
      }
      putServiceDebug(deploymentId, payload?.artifacts, payload?.probe);
    }
  }

  async function handleProbeService(deploymentId: string) {
    try {
      const data = await runAction("health:" + deploymentId, () =>
        getJson("/api/infer/deployments/" + deploymentId + "/service/health")
      );
      const record = asRecord(data);
      if (record?.deployment) {
        upsertDeployment(record.deployment);
      }
      putServiceDebug(deploymentId, record?.artifacts, record?.probe);
      const probe = normalizeServiceProbe(record?.probe);
      const health = asRecord(probe?.healthJson);
      const exitCode = probe?.exitCode;
      const name = normalizeDeployment(record?.deployment).name;
      if (health?.ready === true) {
        setNotice("服务已就绪：" + name);
      } else if (exitCode !== null && exitCode !== undefined) {
        setNotice("已刷新服务状态：" + name + "，exit=" + exitCode);
      } else {
        setNotice("已刷新服务状态：" + name);
      }
    } catch (actionError) {
      const payload = asRecord(extractErrorPayload(actionError));
      if (payload?.deployment) {
        upsertDeployment(payload.deployment);
      }
      putServiceDebug(deploymentId, payload?.artifacts, payload?.probe);
    }
  }

  async function createSession() {
    if (selectedDeploymentId.length === 0) {
      throw new Error("先选择 deployment");
    }
    const data = await runAction("create-session", () =>
      postJson("/api/evals/live/sessions", {
        modelDeploymentId: selectedDeploymentId,
        title: sessionTitle.trim(),
        scenario: scenario.trim(),
      })
    );
    const record = asRecord(data);
    if (record?.session) {
      const session = normalizeSession(record.session);
      upsertSession(record.session);
      setSelectedSessionId(session.id);
      setNotice("已创建会话：" + session.title);
      return session;
    }
    throw new Error("创建 session 失败");
  }

  function onCreateSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void createSession().catch(() => undefined);
  }

  async function sendMessage() {
    const content = messageInput.trim();
    if (content.length === 0) {
      return;
    }

    let targetSessionId = selectedSessionId;
    if (targetSessionId.length === 0) {
      const created = await createSession();
      targetSessionId = created.id;
    }

    try {
      const data = await runAction("send-message", () =>
        postJson("/api/evals/live/sessions/" + targetSessionId + "/chat", {
          content,
          maxNewTokens: Number(maxNewTokens) || 256,
          doSample,
          temperature: Number(temperature) || 0.7,
          topP: Number(topP) || 0.95,
        })
      );

      const record = asRecord(data);
      if (record?.session) {
        const session = normalizeSession(record.session);
        upsertSession(record.session);
        setSelectedSessionId(session.id);
      }
      if (record?.deployment) {
        upsertDeployment(record.deployment);
      }
      putServiceDebug(selectedDeploymentId, record?.artifacts, record?.probe);
      setMessageInput("");
      const assistantTurn = normalizeTurn(record?.assistantTurn);
      setNotice(assistantTurn.latencyMs ? "模型已回复，耗时 " + assistantTurn.latencyMs + " ms" : "模型已回复");
    } catch (actionError) {
      const payload = asRecord(extractErrorPayload(actionError));
      if (payload?.session) {
        upsertSession(payload.session);
      }
      if (payload?.deployment) {
        upsertDeployment(payload.deployment);
      }
      putServiceDebug(selectedDeploymentId, payload?.artifacts, payload?.probe);
    }
  }

  function onSendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage().catch(() => undefined);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">在线服务 Deployment</h2>
            <p className="mt-1 text-sm text-gray-400">先启动 H20 上的常驻推理服务，再创建会话并发送多轮消息。</p>
          </div>
          {selectedDeployment ? (
            <div className="text-sm text-gray-400">当前 deployment: {selectedDeployment.name}</div>
          ) : null}
        </div>
        {deployments.length === 0 ? (
          <div className="rounded-lg bg-amber-600/20 px-4 py-3 text-sm text-amber-100">暂无可在线使用的 deployment。先去推理端点配置支持在线服务的 deployment。</div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {deployments.map((deployment) => {
              const isSelected = deployment.id === selectedDeploymentId;
              const cardClass = [
                "rounded-xl border p-4 text-left transition",
                isSelected ? "border-blue-500 bg-blue-500/10" : "border-gray-800 bg-gray-950 hover:border-gray-700",
              ].join(" ");
              return (
                <button
                  key={deployment.id}
                  type="button"
                  onClick={() => setSelectedDeploymentId(deployment.id)}
                  className={cardClass}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-white">{deployment.name}</div>
                      <div className="mt-1 text-xs text-gray-500">{deployment.slug}</div>
                    </div>
                    <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-medium", statusBadgeClass(deployment.serviceStatus)].join(" ")}>{deployment.serviceStatus}</span>
                  </div>
                  <div className="mt-3 space-y-1 text-sm text-gray-400">
                    <div>Host: {deployment.inferHostName}</div>
                    <div>Mode: {deployment.serviceMode}</div>
                    <div className="text-xs text-gray-500">{shortenPath(deployment.serviceBaseUrl)}</div>
                    {deployment.serviceLastExitCode !== null ? <div className="text-xs text-red-300">Last exit: {deployment.serviceLastExitCode}</div> : null}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleStartService(deployment.id);
                      }}
                      disabled={busyKey.length > 0}
                      className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                    >
                      启动服务
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleProbeService(deployment.id);
                      }}
                      disabled={busyKey.length > 0}
                      className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 disabled:opacity-60"
                    >
                      检查状态
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleStopService(deployment.id);
                      }}
                      disabled={busyKey.length > 0}
                      className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 disabled:opacity-60"
                    >
                      停止服务
                    </button>
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {selectedDeployment ? (
          <div className="rounded-xl border border-gray-800 bg-gray-950 p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">服务诊断</div>
                <div className="mt-1 text-xs text-gray-500">优先展示数据库里最近一次状态；点“检查状态”后会额外显示远端 log tail。</div>
              </div>
              <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-medium", statusBadgeClass(selectedDeployment.serviceStatus)].join(" ")}>{selectedDeployment.serviceStatus}</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-[1.1fr,1.4fr]">
              <div className="space-y-2 text-sm text-gray-300">
                <div>Host: {selectedDeployment.inferHostName}</div>
                <div>Base URL: <span className="text-gray-400">{shortenPath(selectedDeployment.serviceBaseUrl)}</span></div>
                <div>Session: <span className="text-gray-400">{selectedDebug?.artifacts?.sessionName || selectedDeployment.serviceSessionName || "-"}</span></div>
                <div>Log: <span className="text-gray-400">{shortenPath(selectedDebug?.artifacts?.logPath || selectedDeployment.serviceLogPath)}</span></div>
                <div>Status File: <span className="text-gray-400">{shortenPath(selectedDebug?.artifacts?.statusPath || selectedDeployment.serviceStatusPath)}</span></div>
                <div>Last Checked: <span className="text-gray-400">{formatDateTime(selectedDeployment.serviceLastCheckedAt || selectedDebug?.updatedAt || null)}</span></div>
                <div>Last Exit: <span className="text-gray-400">{selectedDebug?.probe?.exitCode ?? selectedDeployment.serviceLastExitCode ?? "-"}</span></div>
                <div>Session State: <span className="text-gray-400">{selectedDebug?.probe?.sessionState || "-"}</span></div>
              </div>
              <div className="space-y-3">
                {selectedDeployment.serviceLastError ? (
                  <div className="rounded-lg bg-red-600/15 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap break-words">{selectedDeployment.serviceLastError}</div>
                ) : null}
                {selectedDeployment.notes ? (
                  <div className="rounded-lg bg-gray-900 px-4 py-3 text-sm text-gray-300 whitespace-pre-wrap break-words">{selectedDeployment.notes}</div>
                ) : null}
                {selectedDebug?.probe?.logTail ? (
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Latest Log Tail</div>
                    <pre className="max-h-60 overflow-auto rounded-lg bg-black/40 p-3 text-xs text-gray-200 whitespace-pre-wrap break-words">{selectedDebug.probe.logTail}</pre>
                  </div>
                ) : null}
                {selectedHealthText ? (
                  <div className="space-y-2">
                    <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Health JSON</div>
                    <pre className="max-h-60 overflow-auto rounded-lg bg-black/40 p-3 text-xs text-gray-200 whitespace-pre-wrap break-words">{selectedHealthText}</pre>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.1fr,1.9fr]">
        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Live Session</h2>
            <p className="mt-1 text-sm text-gray-400">会话元数据会写入数据库，支持保留多轮 transcript。</p>
          </div>

          <form onSubmit={onCreateSession} className="space-y-3">
            <input
              value={sessionTitle}
              onChange={(event) => setSessionTitle(event.target.value)}
              placeholder="会话标题，可留空自动生成"
              className="w-full rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
            />
            <textarea
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
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
              <div className="rounded-lg bg-gray-950 px-4 py-3 text-sm text-gray-400">当前 deployment 还没有 live session。</div>
            ) : (
              filteredSessions.map((session) => {
                const active = session.id === selectedSessionId;
                const itemClass = [
                  "w-full rounded-lg border px-4 py-3 text-left",
                  active ? "border-blue-500 bg-blue-500/10" : "border-gray-800 bg-gray-950 hover:border-gray-700",
                ].join(" ");
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.id)}
                    className={itemClass}
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="font-medium text-white">{session.title}</div>
                      <span className={["inline-flex rounded-full px-2 py-1 text-xs font-medium", statusBadgeClass(session.status)].join(" ")}>{session.status}</span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">{session.modelDeploymentName || "-"} @ {session.inferHostName || "-"}</div>
                    <div className="mt-2 text-xs text-gray-400">{formatDateTime(session.updatedAt)}</div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Transcript</h2>
            <p className="mt-1 text-sm text-gray-400">先做请求响应版；服务已经常驻 H20，下一步再补流式输出。</p>
          </div>

          {selectedSession ? (
            <div className="rounded-lg border border-gray-800 bg-gray-950 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-white">{selectedSession.title}</div>
                  <div className="mt-1 text-xs text-gray-500">{selectedSession.modelDeploymentName || "-"} @ {selectedSession.inferHostName || "-"}</div>
                </div>
                <span className={["inline-flex rounded-full px-2.5 py-1 text-xs font-medium", statusBadgeClass(selectedSession.status)].join(" ")}>{selectedSession.status}</span>
              </div>
              {selectedSession.scenario ? (
                <div className="rounded bg-gray-900 px-3 py-2 text-sm text-gray-300">场景：{selectedSession.scenario}</div>
              ) : null}
              {selectedSession.notes ? (
                <div className="rounded bg-red-600/15 px-3 py-2 text-sm text-red-100 whitespace-pre-wrap break-words">{selectedSession.notes}</div>
              ) : null}
              <div className="max-h-[480px] space-y-3 overflow-y-auto pr-1">
                {selectedSession.turns.length === 0 ? (
                  <div className="rounded bg-gray-900 px-3 py-3 text-sm text-gray-400">还没有消息，直接在下面发送第一条问题。</div>
                ) : (
                  selectedSession.turns.map((turn) => {
                    const turnClass = turn.role === "assistant" ? "rounded-lg px-4 py-3 text-sm bg-blue-500/10 text-blue-50" : "rounded-lg px-4 py-3 text-sm bg-gray-900 text-gray-200";
                    return (
                      <div key={turn.id} className={turnClass}>
                        <div className="mb-2 flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-gray-400">
                          <span>{turn.role}</span>
                          {turn.latencyMs ? <span>{turn.latencyMs} ms</span> : null}
                          {turn.tokenCount ? <span>{turn.tokenCount} tokens</span> : null}
                          <span>{formatDateTime(turn.createdAt)}</span>
                        </div>
                        <div className="whitespace-pre-wrap break-words">{turn.content}</div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-gray-700 bg-gray-950 px-4 py-10 text-sm text-gray-400">先创建一个会话，或者从左侧选择已有会话。</div>
          )}

          <form onSubmit={onSendMessage} className="space-y-3">
            <textarea
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
              placeholder="输入你要模拟连麦发送的问题"
              className="min-h-32 w-full rounded-lg bg-gray-800 px-3 py-3 text-sm text-white"
            />
            <div className="grid gap-3 md:grid-cols-4">
              <input
                value={maxNewTokens}
                onChange={(event) => setMaxNewTokens(event.target.value)}
                className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
              />
              <select
                value={doSample ? "true" : "false"}
                onChange={(event) => setDoSample(event.target.value === "true")}
                className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
              >
                <option value="false">greedy</option>
                <option value="true">sample</option>
              </select>
              <input
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
                className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
              />
              <input
                value={topP}
                onChange={(event) => setTopP(event.target.value)}
                className="rounded-lg bg-gray-800 px-3 py-2 text-sm text-white"
              />
            </div>
            <button
              disabled={busyKey.length > 0 || deployments.length === 0}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              发送消息
            </button>
          </form>
        </section>
      </div>

      {notice.length > 0 || error.length > 0 ? (
        <div className={error.length > 0 ? "rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200" : "rounded-lg bg-emerald-600/20 px-4 py-3 text-sm text-emerald-200"}>
          {error.length > 0 ? error : notice}
        </div>
      ) : null}
    </div>
  );
}
