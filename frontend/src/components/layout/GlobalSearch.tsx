import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { DataSourceBadge } from "@/components/common/common";

interface SearchResult {
  repos: { repo_full_name: string; language: string | null; stars: number; data_source: string }[];
  contributors: { login: string; commits_total: number; repos: number }[];
  issues: { repo_full_name: string; number: number; title: string; state: string }[];
}

export function GlobalSearch() {
  const [value, setValue] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value.trim()), 250);
    return () => clearTimeout(t);
  }, [value]);
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);
  const { data, isFetching } = useQuery({
    queryKey: ["global-search", debounced],
    queryFn: ({ signal }) => api.get<SearchResult>(`/search?q=${encodeURIComponent(debounced)}`, signal),
    enabled: debounced.length >= 2,
  });
  const hasResults = !!data && (data.repos.length + data.contributors.length + data.issues.length > 0);
  const go = (to: string) => { setOpen(false); setValue(""); navigate(to); };
  return (
    <div ref={ref} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
      <input
        value={value}
        onChange={(e) => { setValue(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" && data?.repos[0]) go(`/repos/${data.repos[0].repo_full_name}`); if (e.key === "Escape") setOpen(false); }}
        placeholder="Search repos, contributors, issues…   ⌘K"
        aria-label="Global search"
        className="h-10 w-full rounded-xl border border-white/10 bg-ink-900/70 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400/50 focus:outline-none focus:ring-2 focus:ring-cyan-400/15"
      />
      {open && debounced.length >= 2 && (
        <div className="glass-strong absolute left-0 right-0 top-12 z-50 max-h-96 overflow-y-auto rounded-xl p-2 shadow-2xl scrollbar-thin" role="listbox">
          {isFetching && !data && <p className="px-3 py-2 text-xs text-slate-500">Searching…</p>}
          {data && !hasResults && <p className="px-3 py-2 text-xs text-slate-500">No results for “{debounced}”.</p>}
          {data?.repos.length ? <Group title="Repositories">{data.repos.map((r) => (
            <Item key={r.repo_full_name} onClick={() => go(`/repos/${r.repo_full_name}`)} label={r.repo_full_name} meta={`${r.language ?? "—"} · ★ ${r.stars}`} source={r.data_source} />
          ))}</Group> : null}
          {data?.contributors.length ? <Group title="Contributors">{data.contributors.map((c) => (
            <Item key={c.login} onClick={() => go(`/contributors?login=${encodeURIComponent(c.login)}`)} label={c.login} meta={`${c.commits_total} commits · ${c.repos} repo(s)`} />
          ))}</Group> : null}
          {data?.issues.length ? <Group title="Issues">{data.issues.map((i) => (
            <Item key={`${i.repo_full_name}#${i.number}`} onClick={() => go(`/repos/${i.repo_full_name}?tab=issues`)} label={`#${i.number} ${i.title}`} meta={`${i.repo_full_name} · ${i.state}`} />
          ))}</Group> : null}
        </div>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="mb-1"><p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{title}</p>{children}</div>;
}

function Item({ label, meta, onClick, source }: { label: string; meta: string; onClick: () => void; source?: string }) {
  return (
    <button onClick={onClick} className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left transition hover:bg-white/5">
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-slate-100">{label}</span>
        <span className="block truncate text-[11px] text-slate-500">{meta}</span>
      </span>
      <DataSourceBadge source={source} />
    </button>
  );
}
