export function formatDateTime(value: Date | string | null | undefined) {
  if (!value) return "-";
  const date = typeof value === "string" ? new Date(value) : value;
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(date);
}

export function statusBadgeClass(status: string) {
  switch (status) {
    case "active":
    case "succeeded":
    case "ready":
    case "running_service":
      return "bg-emerald-600/20 text-emerald-300";
    case "queued":
    case "running":
    case "starting":
      return "bg-sky-600/20 text-sky-300";
    case "draft":
    case "stopped":
      return "bg-gray-700/40 text-gray-300";
    case "failed":
    case "failed_launch":
    case "error":
      return "bg-red-600/20 text-red-300";
    default:
      return "bg-amber-600/20 text-amber-200";
  }
}

export function formatJsonText(value: string | null | undefined) {
  if (!value) return null;
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

export function shortenPath(value: string | null | undefined, max = 96) {
  if (!value) return "-";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 16)}...${value.slice(-12)}`;
}

export function severityBadgeClass(severity: string) {
  switch (severity) {
    case "critical":
      return "bg-rose-600/20 text-rose-300";
    case "high":
      return "bg-orange-600/20 text-orange-300";
    case "medium":
      return "bg-amber-600/20 text-amber-200";
    case "low":
      return "bg-gray-700/40 text-gray-300";
    default:
      return "bg-gray-700/40 text-gray-300";
  }
}
