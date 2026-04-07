import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  buildLiveServiceArtifacts,
  defaultServicePortForSlug,
  nextLiveServiceStatus,
  probeLiveService,
  remoteHttpJson,
  summarizeLiveServiceError,
} from "@/lib/remoteJobs";

export const dynamic = "force-dynamic";

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asBoolean(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value === "true" || value === "1" || value === "on";
  return false;
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

function jsonStringOrNull(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }
  return JSON.stringify(value);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const resolved = await params;
  const session = await prisma.liveSession.findUnique({
    where: { id: resolved.id },
    include: {
      inferHost: true,
      modelDeployment: { include: { inferHost: true } },
      turns: { orderBy: { createdAt: "asc" } },
    },
  });

  if (
    session === null ||
    session === undefined ||
    session.modelDeployment === null ||
    session.modelDeployment === undefined
  ) {
    return NextResponse.json({ error: "Live session not found" }, { status: 404 });
  }

  const inferHost = session.inferHost || session.modelDeployment.inferHost;
  if (inferHost === null || inferHost === undefined) {
    return NextResponse.json({ error: "Infer host not found" }, { status: 400 });
  }

  const body = await request.json().catch(() => ({}));
  const content = asString(body.content);
  if (content.length === 0) {
    return NextResponse.json({ error: "content is required" }, { status: 400 });
  }

  const userTurn = await prisma.liveTurn.create({
    data: {
      liveSessionId: session.id,
      role: "user",
      content,
    },
  });

  const port = resolvePort(session.modelDeployment.serviceBaseUrl, session.modelDeployment.slug);
  const artifacts = buildLiveServiceArtifacts(inferHost.workspacePath, session.modelDeployment.slug, port);
  const chatUrl = artifacts.baseUrl + (session.modelDeployment.serviceChatPath || "/chat");
  const messages = session.turns.map((turn) => ({ role: turn.role, content: turn.content }));
  messages.push({ role: "user", content });

  try {
    const result = await remoteHttpJson({
      host: {
        sshHost: inferHost.sshHost,
        sshPort: inferHost.sshPort,
        sshUser: inferHost.sshUser,
        workspacePath: inferHost.workspacePath,
      },
      url: chatUrl,
      method: "POST",
      body: {
        messages,
        max_new_tokens: asNumber(body.maxNewTokens, 256),
        do_sample: asBoolean(body.doSample),
        temperature: asNumber(body.temperature, 0.7),
        top_p: asNumber(body.topP, 0.95),
      },
    });

    const payload = typeof result === "object" && result !== null ? (result as Record<string, unknown>) : {};
    const outputText = asString(payload.output_text) || asString(payload.raw_output_text);
    const assistantTurn = await prisma.liveTurn.create({
      data: {
        liveSessionId: session.id,
        role: "assistant",
        content: outputText,
        latencyMs: asNumber(payload.latency_ms, 0),
        tokenCount: asNumber(payload.generated_tokens, 0),
        rawJson: JSON.stringify(result),
      },
    });

    const transcript = messages.concat([{ role: "assistant", content: outputText }]);
    const [updatedSession, updatedDeployment] = await Promise.all([
      prisma.liveSession.update({
        where: { id: session.id },
        data: {
          status: "active",
          transcriptJson: JSON.stringify(transcript),
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          turns: { orderBy: { createdAt: "asc" } },
        },
      }),
      prisma.modelDeployment.update({
        where: { id: session.modelDeployment.id },
        data: {
          serviceStatus: "running_service",
          serviceBaseUrl: artifacts.baseUrl,
          serviceChatPath: "/chat",
          serviceSessionName: artifacts.sessionName,
          serviceLogPath: artifacts.logPath,
          serviceStatusPath: artifacts.statusPath,
          serviceLastExitCode: null,
          serviceLastError: null,
          serviceLastCheckedAt: new Date(),
        },
        include: { inferHost: true },
      }),
    ]);

    return NextResponse.json({ session: updatedSession, userTurn, assistantTurn, result, deployment: updatedDeployment, artifacts });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const probe = await probeLiveService({
      host: {
        sshHost: inferHost.sshHost,
        sshPort: inferHost.sshPort,
        sshUser: inferHost.sshUser,
        workspacePath: inferHost.workspacePath,
      },
      sessionName: artifacts.sessionName,
      statusPath: artifacts.statusPath,
      logPath: artifacts.logPath,
      baseUrl: artifacts.baseUrl,
    }).catch(() => null);

    const [updatedSession, updatedDeployment] = await Promise.all([
      prisma.liveSession.update({
        where: { id: session.id },
        data: {
          status: "error",
          notes: [session.notes, "live_chat_error=" + message].filter(Boolean).join("\n"),
        },
        include: {
          inferHost: true,
          modelDeployment: true,
          turns: { orderBy: { createdAt: "asc" } },
        },
      }),
      prisma.modelDeployment.update({
        where: { id: session.modelDeployment.id },
        data: {
          serviceStatus: probe ? nextLiveServiceStatus(probe) : "failed",
          serviceBaseUrl: artifacts.baseUrl,
          serviceChatPath: "/chat",
          serviceSessionName: artifacts.sessionName,
          serviceLogPath: artifacts.logPath,
          serviceStatusPath: artifacts.statusPath,
          serviceLastExitCode: probe?.exitCode ?? null,
          serviceLastError: [message, probe ? summarizeLiveServiceError(probe) : null]
            .filter((item, index, items) => Boolean(item) && items.indexOf(item) === index)
            .join(" | "),
          serviceLastHealthJson: jsonStringOrNull(probe?.healthJson),
          serviceLastCheckedAt: new Date(),
        },
        include: { inferHost: true },
      }),
    ]);

    return NextResponse.json(
      { error: message, session: updatedSession, deployment: updatedDeployment, probe, artifacts },
      { status: 502 }
    );
  }
}
