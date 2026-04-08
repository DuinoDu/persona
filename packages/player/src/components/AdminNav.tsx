import Link from "next/link";

const ITEMS = [
  { href: "/", label: "播放器" },
  { href: "/admin/feedback", label: "反馈后台" },
  { href: "/admin/evals", label: "评测中心" },
  { href: "/admin/evals/bad-cases", label: "评测坏例" },
  { href: "/admin/evals/exports", label: "导出" },
  { href: "/admin/evals/arena", label: "Arena" },
  { href: "/admin/infer/endpoints", label: "推理端点" },
  { href: "/admin/evals/live", label: "在线 Infer" },
];

export function AdminNav({ current }: { current?: string }) {
  return (
    <nav className="flex flex-wrap items-center gap-2">
      {ITEMS.map((item) => {
        const active = current === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={
              active
                ? "rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white"
                : "rounded-lg bg-gray-800 px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition"
            }
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
