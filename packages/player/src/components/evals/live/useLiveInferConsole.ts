"use client";

import { useEffect, useState } from "react";
import { extractErrorPayload, getJson, postJson, postSse } from "./client";
import {
  asNullableNumber,
  asRecord,
  asString,
  type DeploymentItem,
  type LiveSessionItem,
  normalizeDeployment,
  normalizeServiceArtifacts,
  normalizeServiceProbe,
  normalizeSession,
  normalizeTurn,
  type ServiceDebugState,
} from "./types";

export function useLiveInferConsole(input: {
  initialDeployments: DeploymentItem[];
  initialSessions: LiveSessionItem[];
}) {
  const { initialDeployments, initialSessions } = input;
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
  const [streamingSessionId, setStreamingSessionId] = useState("");
  const [streamingAssistantText, setStreamingAssistantText] = useState("");
  const [streamingUserText, setStreamingUserText] = useState("");
  const [streamingLatencyMs, setStreamingLatencyMs] = useState<number | null>(null);
  const [streamingTokenCount, setStreamingTokenCount] = useState<number | null>(null);

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
  const selectedDeploymentIsStarting = selectedDeployment?.serviceStatus === "starting";
  const filteredSessions = sessions.filter((item) => {
    if (selectedDeploymentId.length === 0) {
      return true;
    }
    return item.modelDeploymentId === selectedDeploymentId;
  });

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

  async function refreshServiceHealth(
    deploymentId: string,
    options: { silent?: boolean } = {}
  ) {
    try {
      const data = options.silent
        ? await getJson("/api/infer/deployments/" + deploymentId + "/service/health")
        : await runAction("health:" + deploymentId, () =>
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
      if (options.silent) {
        return;
      }
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
      if (options.silent) {
        return;
      }
      throw actionError;
    }
  }

  useEffect(() => {
    if (!selectedDeploymentId || !selectedDeploymentIsStarting) {
      return;
    }
    void refreshServiceHealth(selectedDeploymentId, { silent: true });
    const timer = window.setInterval(() => {
      void refreshServiceHealth(selectedDeploymentId, { silent: true });
    }, 5000);
    return () => {
      window.clearInterval(timer);
    };
  }, [selectedDeploymentId, selectedDeploymentIsStarting]);

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
      const skipped = record?.skipped === true;
      const reason = asString(record?.reason);
      const deploymentName = normalizeDeployment(record?.deployment).name;
      if (skipped) {
        if (reason === "already_running") {
          setNotice("服务已在运行，无需重启：" + deploymentName);
          return;
        }
        if (reason === "already_starting") {
          setNotice("服务正在启动，无需重复启动：" + deploymentName);
          return;
        }
      }
      setNotice(
        "已启动服务，H20 冷启动通常需要 3 到 5 分钟；首次发送会自动等待 ready：" +
          deploymentName
      );
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
    void refreshServiceHealth(deploymentId).catch(() => undefined);
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

    setBusyKey("send-message");
    setNotice(
      selectedDeploymentIsStarting
        ? "消息已发送，正在等待 H20 冷启动完成并返回首个 token..."
        : "消息已发送，正在等待 H20 回复..."
    );
    setError("");
    setStreamingSessionId(targetSessionId);
    setStreamingUserText(content);
    setStreamingAssistantText("");
    setStreamingLatencyMs(null);
    setStreamingTokenCount(null);

    try {
      await postSse(
        "/api/evals/live/sessions/" + targetSessionId + "/stream",
        {
          content,
          maxNewTokens: Number(maxNewTokens) || 256,
          doSample,
          temperature: Number(temperature) || 0.7,
          topP: Number(topP) || 0.95,
        },
        (event) => {
          const type = asString(event.type);
          if (type === "chunk") {
            setStreamingAssistantText((value) => value + asString(event.delta));
            setStreamingTokenCount(asNullableNumber(event.generated_tokens));
            return;
          }
          if (type === "done") {
            setStreamingAssistantText(asString(event.output_text) || asString(event.raw_output_text));
            setStreamingLatencyMs(asNullableNumber(event.latency_ms));
            setStreamingTokenCount(asNullableNumber(event.generated_tokens));
            return;
          }
          if (type === "persisted") {
            if (event.session) {
              const session = normalizeSession(event.session);
              upsertSession(event.session);
              setSelectedSessionId(session.id);
            }
            if (event.deployment) {
              upsertDeployment(event.deployment);
            }
            putServiceDebug(selectedDeploymentId, event.artifacts, event.probe);
            setMessageInput("");
            const assistantTurn = normalizeTurn(event.assistantTurn);
            setNotice(
              assistantTurn.latencyMs
                ? "模型已流式回复，耗时 " + assistantTurn.latencyMs + " ms"
                : "模型已流式回复"
            );
            setStreamingSessionId("");
            setStreamingUserText("");
            setStreamingAssistantText("");
            setStreamingLatencyMs(null);
            setStreamingTokenCount(null);
            return;
          }
          if (type === "error") {
            if (event.session) {
              upsertSession(event.session);
            }
            if (event.deployment) {
              upsertDeployment(event.deployment);
            }
            putServiceDebug(selectedDeploymentId, event.artifacts, event.probe);
            setError(asString(event.error) || "流式推理失败");
            setStreamingSessionId("");
            setStreamingUserText("");
            setStreamingAssistantText("");
            setStreamingLatencyMs(null);
            setStreamingTokenCount(null);
          }
        }
      );
    } catch (actionError) {
      const payload = asRecord(extractErrorPayload(actionError));
      if (payload?.session) {
        upsertSession(payload.session);
      }
      if (payload?.deployment) {
        upsertDeployment(payload.deployment);
      }
      putServiceDebug(selectedDeploymentId, payload?.artifacts, payload?.probe);
      setStreamingSessionId("");
      setStreamingUserText("");
      setStreamingAssistantText("");
      setStreamingLatencyMs(null);
      setStreamingTokenCount(null);
    } finally {
      setBusyKey("");
    }
  }

  return {
    deployments,
    sessions,
    selectedDeploymentId,
    setSelectedDeploymentId,
    selectedSessionId,
    setSelectedSessionId,
    sessionTitle,
    setSessionTitle,
    scenario,
    setScenario,
    messageInput,
    setMessageInput,
    maxNewTokens,
    setMaxNewTokens,
    temperature,
    setTemperature,
    topP,
    setTopP,
    doSample,
    setDoSample,
    busyKey,
    notice,
    setNotice,
    error,
    setError,
    serviceDebugByDeploymentId,
    streamingSessionId,
    streamingAssistantText,
    streamingUserText,
    streamingLatencyMs,
    streamingTokenCount,
    selectedDeployment,
    selectedSession,
    selectedDebug,
    selectedDeploymentIsStarting,
    filteredSessions,
    handleStartService,
    handleStopService,
    handleProbeService,
    createSession,
    sendMessage,
  };
}
