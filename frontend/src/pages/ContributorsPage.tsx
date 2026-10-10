import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Card, CardHeader, Select } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Loading, PageHeader, Stat } from "@/components/common/common";
import { CalendarHeatmap } from "@/components/charts/charts";
import { api, downloadExport } from "@/lib/api";
import { num, pct, timeAgo } from "@/lib/format";
import { useGlobalFilters } from "@/lib/filters";
import type { ContributorDetail, ContributorRow, Page, RepoListItem } from "@/lib/types";
import { Download } from "lucide-react";
import { useQuery as useQ } from "@tanstack/react-query";

export default function ContributorsPage() {
  const [params, setParams] = useSearchParams();
  const { filters } = useGlobalFilters();
  const repo = params.get("repo") ?? "";
  const login = params.get("login");
  const setParam = (k: string, v: string | null) => setParams((p) => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n; }, { replace: true });

  const repoOptions = useQ({ queryKey: ["repo-options"], queryFn: ({ signal }) => api.get<Page<RepoListItem>>("/repos?page_size=100&sort=name&order=asc", signal), staleTime: 120_000 });
  const contributors = useQuery({
    queryKey: ["contributors", repo],
    queryFn: ({ signal }) => api.get<{ items: ContributorRow[] }>(`/contributors?limit=200${repo ? `&repo=${encodeURIComponent(repo)}` : ""}`, signal),
  });

  return (
    <>
      <PageHeader eyebrow="People" title="Contributors" description="Who is shipping. Activity is counted from commits attributed to GitHub logins; bots and unattributed commits are excluded."
        actions={<>
          <Select aria-label="Repository" value={repo} onChange={(e) => setParam("repo", e.target.value || null)} className="w-64">
            <option value="" className="bg-ink-900">All repositories</option>
            {repoOptions.data?.items.map((r) => <option key={r.repo_full_name} value={r.repo_full_name} className="bg-ink-900">{r.repo_full_name}</option>)}
          </Select>
        </>} />
      <div className={login ? "grid gap-4 xl:grid-cols-3" : "grid gap-4"}>
        <Card className={login ? "xl:col-span-2" : ""}>
          <CardHeader title="Leaderboard" subtitle={`${contributors.data?.items.length ?? 0} contributors`} />
          <div className="overflow-x-auto p-5 pt-3">
            {contributors.isLoading ? <Loading rows={6} /> : contributors.error ? <ErrorState error={contributors.error} onRetry={() => contributors.refetch()} /> :
              !contributors.data?.items.length ? <EmptyState title="No contributors yet" body="Run the pipeline to ingest commit authors." /> :
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">#</th><th>Login</th><th className="text-right">Commits</th><th className="text-right">30d</th><th className="text-right">Active days</th><th className="text-right">Last commit</th></tr></thead>
                <tbody className="divide-y divide-white/5">
                  {contributors.data.items.map((c) => (
                    <tr key={c.login} onClick={() => setParam("login", c.login)} className={`cursor-pointer transition hover:bg-white/[0.03] ${login === c.login ? "bg-cyan-400/5" : ""}`}>
                      <td className="py-2.5 text-slate-500">{c.rank}</td>
                      <td className="py-2.5 font-medium text-slate-100">@{c.login}{c.repos !== undefined && <span className="ml-2 text-xs font-normal text-slate-500">{c.repos} repo(s)</span>}{c.basis === "contributions_all_time" && <span className="ml-2 rounded border border-white/10 px-1.5 py-0.5 text-[10px] font-normal uppercase tracking-wide text-slate-400" title="Lifetime contribution count reported by GitHub; no commits fall inside the sync window">all-time</span>}</td>
                      <td className="text-right tabular-nums">{num(c.commits_total)}</td>
                      <td className="text-right tabular-nums text-slate-400">{num(c.commits_30d)}</td>
                      <td className="text-right tabular-nums text-slate-400">{num(c.active_days)}</td>
                      <td className="text-right text-xs text-slate-500">{timeAgo(c.last_commit_at)}</td>
                    </tr>))}
                </tbody>
              </table>}
          </div>
        </Card>
        {login && <ContributorPanel login={login} days={filters.days} onClose={() => setParam("login", null)} />}
      </div>
    </>
  );
}

function ContributorPanel({ login, days, onClose }: { login: string; days: number; onClose: () => void }) {
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["contributor", login],
    queryFn: ({ signal }) => api.get<ContributorDetail>(`/contributors/${encodeURIComponent(login)}`, signal),
    retry: (n, err: any) => (err?.status === 404 ? false : n < 2),
  });
  return (
    <Card className="h-fit">
      <CardHeader title={`@${login}`} subtitle="Contribution profile" action={<Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}><X className="h-4 w-4" /></Button>} />
      <div className="space-y-5 p-5 pt-3">
        {isLoading ? <Loading rows={3} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : data && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Repositories" value={num(data.repos.length)} />
              <Stat label="Commits (all visible)" value={num(data.repos.reduce((a, r) => a + r.commits_total, 0))} />
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Repositories</p>
              <ul className="space-y-2 text-sm">{data.repos.map((r) => (
                <li key={r.repo_full_name} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2">
                  <span className="truncate text-slate-200">{r.repo_full_name}</span>
                  <span className="shrink-0 tabular-nums text-slate-400">{num(r.commits_total)} · {pct(r.share_of_commits * 100)}</span>
                </li>))}</ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Activity calendar</p>
              <CalendarHeatmap data={data.daily} days={Math.min(Math.max(days, 7), 365)} />
            </div>
            <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/contributors?format=csv`, "contributors.csv")}><Download className="h-4 w-4" /> Export all contributors (CSV)</Button>
          </>
        )}
      </div>
    </Card>
  );
}
