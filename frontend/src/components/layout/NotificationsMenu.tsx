import { useQuery } from "@tanstack/react-query";
import { Bell, CircleAlert, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { severityColor, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: ({ signal }) => api.get<{ items: Notification[]; unread: number }>("/notifications", signal),
    refetchInterval: 60_000,
  });
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);
  const count = data?.unread ?? 0;
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-label={`Notifications, ${count} unread`}
        className="relative grid h-10 w-10 cursor-pointer place-items-center rounded-xl text-slate-300 transition hover:bg-white/5">
        <Bell className="h-4.5 w-4.5" />
        {count > 0 && <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">{count}</span>}
      </button>
      {open && (
        <div className="glass-strong absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-2xl shadow-2xl sm:w-96" role="menu">
          <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold text-slate-100">Notifications</div>
          <ul className="scrollbar-thin max-h-96 divide-y divide-white/5 overflow-y-auto">
            {(data?.items ?? []).length === 0 && <li className="px-4 py-8 text-center text-sm text-slate-500">You're all caught up.</li>}
            {(data?.items ?? []).map((n) => (
              <li key={n.id}>
                <Link to={n.link} onClick={() => setOpen(false)} className="flex gap-3 px-4 py-3 transition hover:bg-white/5">
                  <span className={cn("mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border", severityColor(n.severity))}>
                    {n.type === "pipeline" ? <Workflow className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-100">{n.title}</span>
                    <span className="line-clamp-2 text-xs text-slate-400">{n.message}</span>
                    <span className="mt-0.5 block text-[10px] text-slate-500">{n.created_at ? timeAgo(n.created_at) : ""}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
