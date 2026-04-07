import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  buildLiveServiceArtifacts,
  defaultServicePortForSlug,
  launchLiveService,
} from "@/lib/remoteJobs";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function resolvePort(baseUrl: string | null, slug: string) {
  if (baseUrl) {
    try {
      const url = new URL(baseUrl);
      const parsed = Number(url.port);
      if (Number.isFinite(parsed) && parsed > 0) {
        return parsed;
      }
    } catch {
      // ignore malformed url and fall back to slug-derived port
    }
  }
  return defaultServicePortForSlug(slug);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const resolved = await params;
  const deployment = await prisma.modelDeployment.findUnique({
    where: { id: resolved.id },
    include: { inferHost: true },
  });

  if (
    deployment === null ||
    deployment === undefined ||
    deployment.inferHost === null ||
    deployment.inferHost === undefined
  ) {
    return NextResponse.json({ error: "Deployment not found" }, { status: 404 });
  }

  if (deployment.serviceMode === "offline_only") {
    return NextResponse.json({ error: "Deployment is offline_only" }, { status: 400 });
  }

  const body = await request.json().catch(() => ({}));
  const port = asNumber(body.port, resolvePort(deployment.serviceBaseUrl, deployment.slug));
  const device = asString(body.device) || deployment.defaultDevice;
  const host = asString(body.host) || "127.0.0.1";
  const maxNewTokensDefault = asNumber(body.maxNewTokensDefault, 256);
  const systemPromptFile = asString(body.systemPromptFile) || deployment.systemPromptFile || undefined;
  const artifacts = buildLiveServiceArtifacts(deployment.inferHost.workspacePath, deployment.slug, port);

  try {
    const launch = await launchLiveService({
      host: {
        sshHost: deployment.inferHost.sshHost,
        sshPort: deployment.inferHost.sshPort,
        sshUser: deployment.inferHost.sshUser,
        workspacePath: deployment.inferHost.workspacePath,
      },
      deployment: {
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerScriptPath: deployment.runnerScriptPath,
        defaultDevice: deployment.defaultDevice,
        slug: deployment.slug,
      },
      config: {
        port,
        host,
        device,
        maxNewTokensDefault,
        systemPromptFile,
      },
    });

    const updated = await prisma.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "starting",
        serviceBaseUrl: launch.baseUrl,
        serviceChatPath: "/chat",
        serviceStreamPath: null,
        serviceSessionName: launch.sessionName,
        serviceLogPath: launch.logPath,
        serviceStatusPath: launch.statusPath,
        serviceLastExitCode: null,
        serviceLastError: null,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });

    return NextResponse.json({ deployment: updated, launch, artifacts: launch });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const updated = await prisma.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "failed_launch",
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: "/chat",
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: null,
        serviceLastError: message,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });
    return NextResponse.json({ error: message, deployment: updated, artifacts }, { status: 500 });
  }
}
