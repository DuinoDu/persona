import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  buildLiveServiceArtifacts,
  defaultServicePortForSlug,
  nextLiveServiceStatus,
  probeLiveService,
  summarizeLiveServiceError,
} from "@/lib/remoteJobs";

export const dynamic = "force-dynamic";

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

function jsonStringOrNull(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }
  return JSON.stringify(value);
}

export async function GET(
  _request: Request,
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

  const port = resolvePort(deployment.serviceBaseUrl, deployment.slug);
  const artifacts = buildLiveServiceArtifacts(
    deployment.inferHost.workspacePath,
    deployment.slug,
    port
  );

  try {
    const probe = await probeLiveService({
      host: {
        sshHost: deployment.inferHost.sshHost,
        sshPort: deployment.inferHost.sshPort,
        sshUser: deployment.inferHost.sshUser,
        workspacePath: deployment.inferHost.workspacePath,
      },
      sessionName: artifacts.sessionName,
      statusPath: artifacts.statusPath,
      logPath: artifacts.logPath,
      baseUrl: artifacts.baseUrl,
    });

    const updated = await prisma.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: nextLiveServiceStatus(probe),
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: "/chat",
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastExitCode: probe.exitCode,
        serviceLastError: summarizeLiveServiceError(probe),
        serviceLastHealthJson: jsonStringOrNull(probe.healthJson),
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });

    return NextResponse.json({ deployment: updated, probe, artifacts });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const updated = await prisma.modelDeployment.update({
      where: { id: deployment.id },
      data: {
        serviceStatus: "error",
        serviceBaseUrl: artifacts.baseUrl,
        serviceChatPath: "/chat",
        serviceSessionName: artifacts.sessionName,
        serviceLogPath: artifacts.logPath,
        serviceStatusPath: artifacts.statusPath,
        serviceLastError: message,
        serviceLastHealthJson: null,
        serviceLastCheckedAt: new Date(),
      },
      include: { inferHost: true },
    });
    return NextResponse.json({ error: message, deployment: updated, artifacts }, { status: 500 });
  }
}
