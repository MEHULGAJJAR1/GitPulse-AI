import { motion } from "framer-motion";
import { Activity, BarChart3, Bot, FileDown, GitBranch, LayoutDashboard, LogOut, PanelLeftClose, PanelLeftOpen, Settings, Users, Workflow } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

const NAV: { to: string; label: string; icon: typeof LayoutDashboard; min: Role }[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, min: "viewer" },
  { to: "/repos", label: "Repositories", icon: GitBranch, min: "viewer" },
  { to: "/contributors", label: "Contributors", icon: Users, min: "viewer" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, min: "viewer" },
  { to: "/assistant", label: "AI Assistant", icon: Bot, min: "viewer" },
  { to: "/reports", label: "Reports & Export", icon: FileDown, min: "viewer" },
  { to: "/pipelines", label: "Pipelines", icon: Workflow, min: "viewer" },
  { to: "/settings", label: "Settings", icon: Settings, min: "viewer" },
];

export function Sidebar({ collapsed, onToggle, onNavigate }: { collapsed: boolean; onToggle: () => void; onNavigate?: () => void }) {
  const { can, me, logout } = useAuth();
  return (
    <motion.aside
      animate={{ width: collapsed ? 76 : 248 }}
      transition={{ type: "spring", stiffness: 260, damping: 30 }}
      className="glass-strong flex h-full flex-col border-r border-white/10"
      aria-label="Primary"
    >
      <div className="flex h-16 items-center gap-3 px-4">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-violet-500 shadow-lg shadow-cyan-500/30">
          <Activity className="h-5 w-5 text-ink-950" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-white">GitPulse</div>
            <div className="truncate text-[11px] text-slate-500">GitHub analytics · ELT</div>
          </div>
        )}
      </div>
      <nav className="scrollbar-thin flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {NAV.filter((n) => can(n.min)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              cn(
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-100",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <motion.span layoutId="nav-active" className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-gradient-to-b from-cyan-300 to-violet-400" />}
                <item.icon className={cn("h-4.5 w-4.5 shrink-0", isActive && "text-cyan-300")} />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-2 border-t border-white/10 p-3">
        {!collapsed && me && (
          <div className="rounded-xl bg-white/5 px-3 py-2 text-xs text-slate-400">
            Signed in as <span className="font-semibold capitalize text-slate-200">{me.role}</span>
            {me.can_see_private_repos && <div className="text-[11px] text-violet-300">private repos enabled</div>}
          </div>
        )}
        <div className="flex items-center gap-2">
          <button onClick={onToggle} className="flex h-9 flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl text-slate-400 transition hover:bg-white/5 hover:text-white" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" /><span className="text-xs">Collapse</span></>}
          </button>
          {!collapsed && (
            <button onClick={logout} className="flex h-9 cursor-pointer items-center gap-2 rounded-xl px-3 text-xs text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-200" aria-label="Sign out">
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </motion.aside>
  );
}
