import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { launchOfflineEvalJob } from "@/lib/remoteJobs";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asOptionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asBoolean(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value === "true" || value === "on" || value === "1";
  return false;
}

function asNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export async function GET() {
  const items = await prisma.evalRun.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const inferHostId = asString(body.inferHostId);
  const modelDeploymentId = asString(body.modelDeploymentId);
  const evalSuiteId = asString(body.evalSuiteId);
  const autoLaunch = asBoolean(body.autoLaunch);

  if (!inferHostId || !modelDeploymentId || !evalSuiteId) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const [host, deployment, suite] = await Promise.all([
    prisma.inferHost.findUnique({ where: { id: inferHostId } }),
    prisma.modelDeployment.findUnique({ where: { id: modelDeploymentId } }),
    prisma.evalSuite.findUnique({ where: { id: evalSuiteId } }),
  ]);

  if (!host || !deployment || !suite) {
    return NextResponse.json({ error: "Host / Deployment / Suite not found" }, { status: 404 });
  }

  const config = {
    maxNewTokens: asNumber(body.maxNewTokens, 256),
    device: asString(body.device) || deployment.defaultDevice,
    doSample: asBoolean(body.doSample),
    temperature: asNumber(body.temperature, 0.7),
    topP: asNumber(body.topP, 0.95),
    systemPromptFile: asOptionalString(body.systemPromptFile),
    autoLaunch,
  };

  const title = asString(body.title) || `${suite.title} @ ${deployment.name}`;
  let run = await prisma.evalRun.create({
    data: {
      inferHostId,
      modelDeploymentId,
      evalSuiteId,
      title,
      mode: "offline",
      kind: "suite_batch",
      status: autoLaunch ? "queued" : "draft",
      configJson: JSON.stringify(config),
    },
    include: {
      inferHost: true,
      modelDeployment: true,
      evalSuite: true,
    },
  });

  if (!autoLaunch) {
    return NextResponse.json(run);
  }

  try {
    const launch = await launchOfflineEvalJob({
      host: {
        sshHost: host.sshHost,
        sshPort: host.sshPort,
        sshUser: host.sshUser,
        workspacePath: host.workspacePath,
      },
      deployment: {
        baseModelPath: deployment.baseModelPath,
        adapterPath: deployment.adapterPath,
        systemPromptFile: deployment.systemPromptFile,
        runnerScriptPath: deployment.runnerScriptPath,
        defaultDevice: deployment.defaultDevice,
      },
      suite: {
        sourcePath: suite.sourcePath,
        slug: suite.slug,
      },
      runId: run.id,
      config,
    });

    run = await prisma.evalRun.update({
      where: { id: run.id },
      data: {
        status: "running",
        outputDir: launch.outputDir,
        logPath: launch.logPath,
        statusPath: launch.statusPath,
        summaryPath: launch.summaryPath,
        tmuxSession: launch.sessionName,
        remoteCommand: launch.remoteCommand,
        startedAt: new Date(),
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
        status: "failed_launch",
        error: message,
      },
      include: {
        inferHost: true,
        modelDeployment: true,
        evalSuite: true,
      },
    });
  }

  return NextResponse.json(run);
}
