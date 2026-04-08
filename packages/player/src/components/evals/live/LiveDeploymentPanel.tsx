"use client";

import { formatDateTime, shortenPath, statusBadgeClass } from "@/lib/evalAdmin";
import type { DeploymentItem, ServiceDebugState } from "./types";

interface Props {
  deployments: DeploymentItem[];
  selectedDeploymentId: string;
  selectedDeployment: DeploymentItem | null;
  selectedDebug: ServiceDebugState | null;
  selectedHealthText: string | null;
  busyKey: string;
  onSelectDeployment: (deploymentId: string) => void;
  onStartService: (deploymentId: string) => void;
  onProbeService: (deploymentId: string) => void;
  onStopService: (deploymentId: string) => void;
}

export function LiveDeploymentPanel(props: Props) {
  const {
    deployments,
    selectedDeploymentId,
    selectedDeployment,
    selectedDebug,
    selectedHealthText,
    busyKey,
    onSelectDeployment,
    onStartService,
    onProbeService,
    onStopService,
  } = props;

  return (
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
        <div className="rounded-lg bg-amber-600/20 px-4 py-3 text-sm text-amber-100">
          暂无可在线使用的 deployment。先去推理端点配置支持在线服务的 deployment。
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {deployments.map((deployment) => {
            const isSelected = deployment.id === selectedDeploymentId;
            const startDisabled =
              busyKey.length > 0 ||
              deployment.serviceStatus === "starting" ||
              deployment.serviceStatus === "running_service";
            const startLabel =
              deployment.serviceStatus === "running_service"
                ? "服务运行中"
                : deployment.serviceStatus === "starting"
                  ? "启动中..."
                  : "启动服务";
            const cardClass = [
              "rounded-xl border p-4 text-left transition",
              isSelected
                ? "border-blue-500 bg-blue-500/10"
                : "border-gray-800 bg-gray-950 hover:border-gray-700",
            ].join(" ");

            return (
              <button
                key={deployment.id}
                type="button"
                onClick={() => onSelectDeployment(deployment.id)}
                className={cardClass}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-medium text-white">{deployment.name}</div>
                    <div className="mt-1 text-xs text-gray-500">{deployment.slug}</div>
                  </div>
                  <span
                    className={[
                      "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                      statusBadgeClass(deployment.serviceStatus),
                    ].join(" ")}
                  >
                    {deployment.serviceStatus}
                  </span>
                </div>
                <div className="mt-3 space-y-1 text-sm text-gray-400">
                  <div>Host: {deployment.inferHostName}</div>
                  <div>Mode: {deployment.serviceMode}</div>
                  <div className="text-xs text-gray-500">{shortenPath(deployment.serviceBaseUrl)}</div>
                  {deployment.serviceLastExitCode !== null ? (
                    <div className="text-xs text-red-300">Last exit: {deployment.serviceLastExitCode}</div>
                  ) : null}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onStartService(deployment.id);
                    }}
                    disabled={startDisabled}
                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                  >
                    {startLabel}
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onProbeService(deployment.id);
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
                      onStopService(deployment.id);
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
              <div className="mt-1 text-xs text-gray-500">
                优先展示数据库里最近一次状态；点“检查状态”后会额外显示远端 log tail。
              </div>
            </div>
            <span
              className={[
                "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                statusBadgeClass(selectedDeployment.serviceStatus),
              ].join(" ")}
            >
              {selectedDeployment.serviceStatus}
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-[1.1fr,1.4fr]">
            <div className="space-y-2 text-sm text-gray-300">
              <div>Host: {selectedDeployment.inferHostName}</div>
              <div>
                Base URL: <span className="text-gray-400">{shortenPath(selectedDeployment.serviceBaseUrl)}</span>
              </div>
              <div>
                Session:{" "}
                <span className="text-gray-400">
                  {selectedDebug?.artifacts?.sessionName || selectedDeployment.serviceSessionName || "-"}
                </span>
              </div>
              <div>
                Log:{" "}
                <span className="text-gray-400">
                  {shortenPath(selectedDebug?.artifacts?.logPath || selectedDeployment.serviceLogPath)}
                </span>
              </div>
              <div>
                Status File:{" "}
                <span className="text-gray-400">
                  {shortenPath(selectedDebug?.artifacts?.statusPath || selectedDeployment.serviceStatusPath)}
                </span>
              </div>
              <div>
                Last Checked:{" "}
                <span className="text-gray-400">
                  {formatDateTime(selectedDeployment.serviceLastCheckedAt || selectedDebug?.updatedAt || null)}
                </span>
              </div>
              <div>
                Last Exit:{" "}
                <span className="text-gray-400">
                  {selectedDebug?.probe?.exitCode ?? selectedDeployment.serviceLastExitCode ?? "-"}
                </span>
              </div>
              <div>
                Session State:{" "}
                <span className="text-gray-400">{selectedDebug?.probe?.sessionState || "-"}</span>
              </div>
            </div>
            <div className="space-y-3">
              {selectedDeployment.serviceLastError ? (
                <div className="rounded-lg bg-red-600/15 px-4 py-3 text-sm text-red-100 whitespace-pre-wrap break-words">
                  {selectedDeployment.serviceLastError}
                </div>
              ) : null}
              {selectedDeployment.notes ? (
                <div className="rounded-lg bg-gray-900 px-4 py-3 text-sm text-gray-300 whitespace-pre-wrap break-words">
                  {selectedDeployment.notes}
                </div>
              ) : null}
              {selectedDebug?.probe?.logTail ? (
                <div className="space-y-2">
                  <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Latest Log Tail</div>
                  <pre className="max-h-60 overflow-auto rounded-lg bg-black/40 p-3 text-xs text-gray-200 whitespace-pre-wrap break-words">
                    {selectedDebug.probe.logTail}
                  </pre>
                </div>
              ) : null}
              {selectedHealthText ? (
                <div className="space-y-2">
                  <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Health JSON</div>
                  <pre className="max-h-60 overflow-auto rounded-lg bg-black/40 p-3 text-xs text-gray-200 whitespace-pre-wrap break-words">
                    {selectedHealthText}
                  </pre>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
