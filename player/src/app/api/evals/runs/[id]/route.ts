import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { probeOfflineEvalJob } from "@/lib/remoteJobs";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  let run = await prisma.evalRun.findUnique({
    where: { id },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!run) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }

  const shouldRefresh = request.nextUrl.searchParams.get("refresh") === "1";
  if (
    shouldRefresh &&
    run.mode === "offline" &&
    run.inferHost &&
    run.tmuxSession &&
    run.statusPath &&
    run.summaryPath &&
    ["queued", "running", "failed_launch", "draft"].includes(run.status) === false
  ) {
    // keep as-is for finished states
  }

  if (
    shouldRefresh &&
    run.mode === "offline" &&
    run.inferHost &&
    run.tmuxSession &&
    run.statusPath &&
    run.summaryPath &&
    ["queued", "running"].includes(run.status)
  ) {
    try {
      const probe = await probeOfflineEvalJob({
        host: {
          sshHost: run.inferHost.sshHost,
          sshPort: run.inferHost.sshPort,
          sshUser: run.inferHost.sshUser,
          workspacePath: run.inferHost.workspacePath,
        },
        tmuxSession: run.tmuxSession,
        statusPath: run.statusPath,
        summaryPath: run.summaryPath,
      });

      let nextStatus = run.status;
      let finishedAt = run.finishedAt;
      if (probe.exitCode !== null) {
        nextStatus = probe.exitCode === 0 ? "succeeded" : "failed";
        finishedAt = finishedAt || new Date();
      } else if (probe.sessionState === "alive") {
        nextStatus = "running";
      }

      run = await prisma.evalRun.update({
        where: { id: run.id },
        data: {
          status: nextStatus,
          finishedAt,
          resultJson: probe.summaryJson || run.resultJson,
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          evalSuite: true,
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      run = await prisma.evalRun.update({
        where: { id: run.id },
        data: {
          error: message,
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          evalSuite: true,
        },
      });
    }
  }

  return NextResponse.json(run);
}
