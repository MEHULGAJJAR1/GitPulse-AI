import { AnimatePresence, motion } from "framer-motion";
import { Bot, BarChart3, FileDown, GitBranch, LayoutDashboard, Search, Settings, Users, Workflow } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: typeof Search;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const { can } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const q = query.trim();
  const search = useQuery({
    queryKey: ["palette-search", q],
    queryFn: ({ signal }) => api.get<{ repos: { repo_full_name: string }[] }>(`/search?q=${encodeURIComponent(q)}`, signal),
    enabled: open && q.length >= 2,
    staleTime: 10_000,
  });

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => { navigate(to); onClose(); };
    const base: Command[] = [
      { id: "overview", label: "Go to Overview", icon: LayoutDashboard, run: go("/") },
      { id: "repos", label: "Go to Repositories", icon: GitBranch, run: go("/repos") },
      { id: "contrib", label: "Go to Contributors", icon: Users, run: go("/contributors") },
      { id: "analytics", label: "Go to Analytics", icon: BarChart3, run: go("/analytics") },
      { id: "ai", label: "Ask the AI assistant", icon: Bot, run: go("/assistant") },
      { id: "reports", label: "Build a report / export data", icon: FileDown, run: go("/reports") },
      { id: "settings", label: "Settings", icon: Settings, run: go("/settings") },
    ];
    if (can("analyst")) base.splice(6, 0, { id: "pipe", label: "Run or monitor pipelines", icon: Workflow, run: go("/pipelines") });
    const repoCmds: Command[] = (search.data?.repos ?? []).map((r) => ({
      id: `repo-${r.repo_full_name}`, label: r.repo_full_name, hint: "Repository", icon: GitBranch,
      run: go(`/repos/${r.repo_full_name}`),
    }));
    const filtered = q ? base.filter((c) => c.label.toLowerCase().includes(q.toLowerCase())) : base;
    return [...repoCmds, ...filtered];
  }, [navigate, onClose, can, search.data, q]);

  useEffect(() => { if (open) { setQuery(""); setActive(0); setTimeout(() => inputRef.current?.focus(), 10); } }, [open]);
  useEffect(() => setActive(0), [query]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, commands.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter" && commands[active]) commands[active].run();
    if (e.key === "Escape") onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} role="dialog" aria-modal="true" aria-label="Command palette">
          <motion.div className="glass-strong w-full max-w-xl overflow-hidden rounded-2xl shadow-2xl"
            initial={{ y: -12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: -8, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b border-white/10 px-4">
              <Search className="h-4 w-4 text-slate-500" />
              <input ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey}
                placeholder="Search repositories, pages, actions…" className="h-12 w-full bg-transparent text-sm text-white placeholder:text-slate-500 focus:outline-none"
                aria-label="Command search" />
              <kbd className="hidden rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-500 sm:block">ESC</kbd>
            </div>
            <ul className="scrollbar-thin max-h-[50vh] overflow-y-auto p-2" role="listbox">
              {commands.length === 0 && <li className="px-3 py-6 text-center text-sm text-slate-500">No matches</li>}
              {commands.map((c, i) => (
                <li key={c.id} role="option" aria-selected={i === active}>
                  <button onMouseEnter={() => setActive(i)} onClick={c.run}
                    className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${i === active ? "bg-white/10 text-white" : "text-slate-300"}`}>
                    <c.icon className="h-4 w-4 text-cyan-300/80" />
                    <span className="flex-1 truncate">{c.label}</span>
                    {c.hint && <span className="text-[11px] text-slate-500">{c.hint}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
