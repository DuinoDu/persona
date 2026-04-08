import { prisma } from "@/lib/db";

const RUN_FAILURE_STATUSES = ["failed", "error", "failed_launch"];
const SERVICE_READY_STATUSES = ["ready", "running_service"];
const SERVICE_FAILURE_STATUSES = ["failed", "failed_launch", "error"];
const ACTIVE_LIVE_SESSION_STATUSES = ["active", "running"];

function daysAgo(days: number) {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000);
}

function withStatusCount(items: Array<{ status: string; _count: { status: number } }>, status: string) {
  return items.find((item) => item.status === status)?._count.status ?? 0;
}

function withStatusCounts(
  items: Array<{ status: string; _count: { status: number } }>,
  statuses: string[]
) {
  return statuses.reduce((sum, status) => sum + withStatusCount(items, status), 0);
}

function withSeverityCount(
  items: Array<{ severity: string; _count: { severity: number } }>,
  severity: string
) {
  return items.find((item) => item.severity === severity)?._count.severity ?? 0;
}

function withStringCount(
  items: Array<{ key: string; _count: { key: number } }>,
  key: string
) {
  return items.find((item) => item.key === key)?._count.key ?? 0;
}

export async function getEvalDashboardOverview() {
  const last7d = daysAgo(7);

  const [
    inferHosts,
    deployments,
    evalSuites,
    evalRuns,
    liveSessions,
    inferenceTraces,
    badCases,
    exports,
    runStatusGroups,
    liveSessionStatusGroups,
    serviceStatusGroups,
    traceStatusGroups,
    traceSourceTypeGroupsRaw,
    badCaseStatusGroups,
    badCaseSeverityGroups,
    exportStatusGroups,
    recentRuns,
    recentBadCases,
    recentExports,
    runsLast7d,
    liveSessionsLast7d,
    tracesLast7d,
    badCasesLast7d,
    exportsLast7d,
    exportReadyBadCases,
    exportedBadCases,
    exportItems,
  ] = await Promise.all([
    prisma.inferHost.count(),
    prisma.modelDeployment.count(),
    prisma.evalSuite.count(),
    prisma.evalRun.count(),
    prisma.liveSession.count(),
    prisma.inferenceTrace.count(),
    prisma.badCase.count(),
    prisma.trainingExport.count(),
    prisma.evalRun.groupBy({
      by: ["status"],
      _count: { status: true },
    }),
    prisma.liveSession.groupBy({
      by: ["status"],
      _count: { status: true },
    }),
    prisma.modelDeployment.groupBy({
      by: ["serviceStatus"],
      _count: { serviceStatus: true },
    }),
    prisma.inferenceTrace.groupBy({
      by: ["status"],
      _count: { status: true },
    }),
    prisma.inferenceTrace.groupBy({
      by: ["sourceType"],
      _count: { sourceType: true },
    }),
    prisma.badCase.groupBy({
      by: ["status"],
      _count: { status: true },
    }),
    prisma.badCase.groupBy({
      by: ["severity"],
      _count: { severity: true },
    }),
    prisma.trainingExport.groupBy({
      by: ["status"],
      _count: { status: true },
    }),
    prisma.evalRun.findMany({
      orderBy: { createdAt: "desc" },
      take: 12,
      include: {
        inferHost: true,
        modelDeployment: true,
        evalSuite: true,
      },
    }),
    prisma.badCase.findMany({
      orderBy: { updatedAt: "desc" },
      take: 8,
      include: {
        modelDeployment: true,
        evalRun: true,
        liveSession: true,
      },
    }),
    prisma.trainingExport.findMany({
      orderBy: { updatedAt: "desc" },
      take: 8,
      include: {
        _count: {
          select: {
            items: true,
          },
        },
      },
    }),
    prisma.evalRun.count({
      where: { createdAt: { gte: last7d } },
    }),
    prisma.liveSession.count({
      where: { updatedAt: { gte: last7d } },
    }),
    prisma.inferenceTrace.count({
      where: { createdAt: { gte: last7d } },
    }),
    prisma.badCase.count({
      where: { createdAt: { gte: last7d } },
    }),
    prisma.trainingExport.count({
      where: { createdAt: { gte: last7d } },
    }),
    prisma.badCase.count({
      where: {
        OR: [
          { editedTargetText: { not: null } },
          {
            AND: [
              { chosenText: { not: null } },
              { rejectedText: { not: null } },
            ],
          },
        ],
      },
    }),
    prisma.badCase.count({
      where: {
        exportItems: {
          some: {},
        },
      },
    }),
    prisma.trainingExportItem.count(),
  ]);

  const traceSourceTypeGroups = traceSourceTypeGroupsRaw.map((item) => ({
    key: item.sourceType,
    _count: { key: item._count.sourceType },
  }));
  const normalizedServiceStatusGroups = serviceStatusGroups.map((item) => ({
    status: item.serviceStatus,
    _count: { status: item._count.serviceStatus },
  }));

  return {
    totals: {
      inferHosts,
      deployments,
      evalSuites,
      evalRuns,
      liveSessions,
      inferenceTraces,
      badCases,
      exports,
    },
    runs: {
      running: withStatusCount(runStatusGroups, "running"),
      queued: withStatusCount(runStatusGroups, "queued"),
      draft: withStatusCount(runStatusGroups, "draft"),
      succeeded: withStatusCount(runStatusGroups, "succeeded"),
      failed: withStatusCounts(runStatusGroups, RUN_FAILURE_STATUSES),
      last7d: runsLast7d,
    },
    live: {
      activeSessions: withStatusCounts(liveSessionStatusGroups, ACTIVE_LIVE_SESSION_STATUSES),
      draftSessions: withStatusCount(liveSessionStatusGroups, "draft"),
      sessionsLast7d: liveSessionsLast7d,
      readyServices: withStatusCounts(normalizedServiceStatusGroups, SERVICE_READY_STATUSES),
      startingServices: withStatusCount(normalizedServiceStatusGroups, "starting"),
      failedServices: withStatusCounts(normalizedServiceStatusGroups, SERVICE_FAILURE_STATUSES),
      stoppedServices: withStatusCount(normalizedServiceStatusGroups, "stopped"),
    },
    traces: {
      offline: withStringCount(traceSourceTypeGroups, "offline_case"),
      live: withStringCount(traceSourceTypeGroups, "live_turn"),
      arena: withStringCount(traceSourceTypeGroups, "arena_pair"),
      errors: withStatusCount(traceStatusGroups, "error"),
      last7d: tracesLast7d,
    },
    flywheel: {
      openBadCases: withStatusCount(badCaseStatusGroups, "open"),
      highSeverityBadCases:
        withSeverityCount(badCaseSeverityGroups, "high") +
        withSeverityCount(badCaseSeverityGroups, "critical"),
      exportReadyBadCases: exportReadyBadCases,
      exportedBadCases,
      badCasesLast7d,
      succeededExports: withStatusCount(exportStatusGroups, "succeeded"),
      runningExports: withStatusCount(exportStatusGroups, "running"),
      failedExports: withStatusCount(exportStatusGroups, "failed"),
      exportsLast7d,
      exportItems,
    },
    recentRuns,
    recentBadCases,
    recentExports,
  };
}
