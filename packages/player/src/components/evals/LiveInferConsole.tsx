"use client";

import { FormEvent } from "react";
import { formatJsonText } from "@/lib/evalAdmin";
import { LiveDeploymentPanel } from "./live/LiveDeploymentPanel";
import { LiveFeedbackBanner } from "./live/LiveFeedbackBanner";
import { LiveSessionSidebar } from "./live/LiveSessionSidebar";
import { LiveTranscriptPanel } from "./live/LiveTranscriptPanel";
import { type LiveInferConsoleProps } from "./live/types";
import { useLiveInferConsole } from "./live/useLiveInferConsole";

export function LiveInferConsole({ deployments: initialDeployments, initialSessions }: LiveInferConsoleProps) {
  const controller = useLiveInferConsole({ initialDeployments, initialSessions });
  const {
    deployments,
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
    error,
    selectedDeployment,
    selectedSession,
    selectedDebug,
    selectedDeploymentIsStarting,
    filteredSessions,
    streamingSessionId,
    streamingAssistantText,
    streamingUserText,
    streamingLatencyMs,
    streamingTokenCount,
    handleStartService,
    handleStopService,
    handleProbeService,
    createSession,
    sendMessage,
  } = controller;

  const selectedHealthText = selectedDebug?.probe?.healthJson
    ? formatJsonText(JSON.stringify(selectedDebug.probe.healthJson))
    : formatJsonText(selectedDeployment?.serviceLastHealthJson);

  function onCreateSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void createSession().catch(() => undefined);
  }

  function onSendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage().catch(() => undefined);
  }

  return (
    <div className="space-y-6">
      <LiveDeploymentPanel
        deployments={deployments}
        selectedDeploymentId={selectedDeploymentId}
        selectedDeployment={selectedDeployment}
        selectedDebug={selectedDebug}
        selectedHealthText={selectedHealthText}
        busyKey={busyKey}
        onSelectDeployment={setSelectedDeploymentId}
        onStartService={(deploymentId) => void handleStartService(deploymentId)}
        onProbeService={(deploymentId) => void handleProbeService(deploymentId)}
        onStopService={(deploymentId) => void handleStopService(deploymentId)}
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr,1.9fr]">
        <LiveSessionSidebar
          selectedDeploymentId={selectedDeploymentId}
          selectedSessionId={selectedSessionId}
          sessionTitle={sessionTitle}
          scenario={scenario}
          busyKey={busyKey}
          filteredSessions={filteredSessions}
          onCreateSession={onCreateSession}
          onSessionTitleChange={setSessionTitle}
          onScenarioChange={setScenario}
          onSelectSession={setSelectedSessionId}
        />

        <LiveTranscriptPanel
          deploymentsCount={deployments.length}
          selectedSession={selectedSession}
          selectedDeploymentIsStarting={selectedDeploymentIsStarting}
          streamingSessionId={streamingSessionId}
          streamingAssistantText={streamingAssistantText}
          streamingUserText={streamingUserText}
          streamingLatencyMs={streamingLatencyMs}
          streamingTokenCount={streamingTokenCount}
          messageInput={messageInput}
          maxNewTokens={maxNewTokens}
          temperature={temperature}
          topP={topP}
          doSample={doSample}
          busyKey={busyKey}
          onSendMessage={onSendMessage}
          onMessageInputChange={setMessageInput}
          onMaxNewTokensChange={setMaxNewTokens}
          onTemperatureChange={setTemperature}
          onTopPChange={setTopP}
          onDoSampleChange={setDoSample}
        />
      </div>

      <LiveFeedbackBanner notice={notice} error={error} />
    </div>
  );
}
