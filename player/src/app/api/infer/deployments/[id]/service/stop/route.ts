import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  buildLiveServiceArtifacts,
  defaultServicePortForSlug,
  stopLiveService,
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

export async function POST(
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

  await stopLiveService({
    host: {
      sshHost: deployment.inferHost.sshHost,
      sshPort: deployment.inferHost.sshPort,
      sshUser: deployment.inferHost.sshUser,
      workspacePath: deployment.inferHost.workspacePath,
    },
    sessionName: artifacts.sessionName,
  });

  const updated = await prisma.modelDeployment.update({
    where: { id: deployment.id },
    data: {
      serviceStatus: "stopped",
      serviceBaseUrl: artifacts.baseUrl,
      serviceChatPath: "/chat",
      serviceSessionName: artifacts.sessionName,
      serviceLogPath: artifacts.logPath,
      serviceStatusPath: artifacts.statusPath,
      serviceLastExitCode: null,
      serviceLastError: null,
      serviceLastHealthJson: null,
      serviceLastCheckedAt: new Date(),
    },
    include: { inferHost: true },
  });

  return NextResponse.json({
    deployment: updated,
    stopped: true,
    sessionName: artifacts.sessionName,
    artifacts,
  });
}
