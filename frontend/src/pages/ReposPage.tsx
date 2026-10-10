import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Input, Select } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { DataModeBanner, DataSourceBadge, EmptyState, ErrorState, Loading, PageHeader } from "@/components/common/common";
import { FilterBar } from "@/components/common/FilterBar";
import { api, downloadExport } from "@/lib/api";
import { compact, gradeColor, hours, num, timeAgo } from "@/lib/format";
import { useGlobalFilters } from "@/lib/filters";
import type { Overview, Page, RepoListItem } from "@/lib/types";

type Sort = "stars" | "commits" | "health" | "name" | "issues" | "merge_time";
const SORTS: { id: Sort; label: string }[] = [
  { id: "stars", label: "Stars" }, { id: "commits", label: "Commits (window)" }, { id: "health", label: "Health" },
  { id: "issues", label: "Open issues" }, { id: "merge_time", label: "Median merge time" }, { id: "name", label: "Name" },
];

export default function ReposPage() {
  const { filters } = useGlobalFilters();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<Sort>("stars");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setQ(search.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => setPage(1), [filters.days, filters.language, filters.dataSource, sort, order]);

  const qs = new URLSearchParams({ days: String(filters.days), sort, order, page: String(page), page_size: "20" });
  if (q) qs.set("q", q);
  if (filters.language) qs.set("language", filters.language);
  if (filters.dataSource) qs.set("data_source", filters.dataSource);

  const repos = useQuery({ queryKey: ["repos", qs.toString()], queryFn: ({ signal }) => api.get<Page<RepoListItem>>(`/repos?${qs}`, signal), placeholderData: (p) => p });
  const overview = useQuery({ queryKey: ["overview-mode", filters.days], queryFn: ({ signal }) => api.get<Overview>(`/dashboard/overview?days=${filters.days}`, signal), staleTime: 60_000 });
  const exportParams = new URLSearchParams({ days: String(filters.days), format: "csv" });
  if (filters.language) exportParams.set("language", filters.language);

  return (
    <>
      <PageHeader eyebrow="Repositories" title="Repositories" description="Every tracked repository with health grade, activity and delivery signals. Click a row for the full analysis."
        actions={<>
          <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/repos?${exportParams}`, "gitpulse-repos.csv")}><Download className="h-4 w-4" /> CSV</Button>
          <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/repos?${new URLSearchParams({ ...Object.fromEntries(exportParams), format: "json" })}`, "gitpulse-repos.json")}><Download className="h-4 w-4" /> JSON</Button>
        </>} />
      {overview.data && <DataModeBanner mode={overview.data.data_mode} />}
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input aria-label="Search repositories" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by name or owner…" className="pl-9" />
        </div>
        <FilterBar />
        <Select aria-label="Sort by" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          {SORTS.map((s) => <option key={s.id} value={s.id} className="bg-ink-900">{s.label}</option>)}
        </Select>
        <Button variant="ghost" size="sm" onClick={() => setOrder((o) => (o === "desc" ? "asc" : "desc"))}>{order === "desc" ? "↓ Desc" : "↑ Asc"}</Button>
      </Card>

      <Card className="overflow-hidden">
        {repos.isLoading ? <div className="p-5"><Loading rows={6} /></div> : repos.error ? <div className="p-5"><ErrorState error={repos.error} onRetry={() => repos.refetch()} /></div> :
          !repos.data?.items.length ? <div className="p-5"><EmptyState title="No repositories match" body="Clear a filter or add a repository on the Pipelines page." /></div> :
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="bg-white/[0.02] text-left text-[11px] uppercase tracking-wider text-slate-500">
                <tr><th className="px-4 py-3">Repository</th><th>Language</th><th className="text-right">Stars</th><th className="text-right">Commits</th><th className="text-right">Contributors</th><th className="text-right">Open issues</th><th className="text-right">Median merge</th><th className="text-right">Last push</th><th className="px-4 text-right">Health</th></tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {repos.data.items.map((r) => (
                  <tr key={r.repo_full_name} className="transition hover:bg-white/[0.03]">
                    <td className="px-4 py-3">
                      <Link to={`/repos/${r.repo_full_name}?days=${filters.days}`} className="font-medium text-slate-100 hover:text-cyan-300">{r.repo_full_name}</Link>
                      <span className="ml-2 align-middle"><DataSourceBadge source={r.data_source} /></span>
                      {r.is_private && <Badge className="ml-2" tone="amber">private</Badge>}
                    </td>
                    <td className="text-slate-400">{r.language ?? "–"}</td>
                    <td className="text-right tabular-nums">{compact(r.stars)}</td>
                    <td className="text-right tabular-nums">{num(r.commits_window)}</td>
                    <td className="text-right tabular-nums text-slate-400">{num(r.contributors)}</td>
                    <td className="text-right tabular-nums text-slate-400">{num(r.open_issues)}</td>
                    <td className="text-right tabular-nums text-slate-400">{hours(r.median_merge_hours)}</td>
                    <td className="text-right text-xs text-slate-500">{timeAgo(r.pushed_at)}</td>
                    <td className="px-4 text-right"><span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${gradeColor(r.grade)}`}>{r.health_score.toFixed(0)} · {r.grade}</span></td>
                  </tr>))}
              </tbody>
            </table>
          </div>}
        {repos.data && (
          <div className="flex items-center justify-between border-t border-white/10 px-4 py-3 text-xs text-slate-400">
            <span>{num(repos.data.total)} repositories · page {repos.data.page} of {repos.data.pages ?? 1}</span>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button variant="ghost" size="sm" disabled={page >= (repos.data.pages ?? 1)} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>)}
      </Card>
    </>
  );
}
