import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, AlertTriangle, CircleDot, GitCommit, GitMerge, GitPullRequest, Star, Timer } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardHeader, Badge } from "@/components/ui/primitives";
import { KpiCard } from "@/components/common/KpiCard";
import { DataModeBanner, EmptyState, ErrorState, PageHeader, Panel, Loading, DataSourceBadge } from "@/components/common/common";
import { FilterBar } from "@/components/common/FilterBar";
import { ActivityTimeline, LanguageDonut } from "@/components/charts/charts";
import { api } from "@/lib/api";
import { compact, gradeColor, hours, num, severityColor, signedPct } from "@/lib/format";
import { useGlobalFilters } from "@/lib/filters";
import type { Overview } from "@/lib/types";

export default function OverviewPage() {
  const { filters } = useGlobalFilters();
  const qs = new URLSearchParams({ days: String(filters.days) });
  if (filters.language) qs.set("language", filters.language);
  if (filters.dataSource) qs.set("data_source", filters.dataSource);
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["overview", filters],
    queryFn: ({ signal }) => api.get<Overview>(`/dashboard/overview?${qs}`, signal),
  });

  const k = data?.kpis;
  return (
    <>
      <PageHeader eyebrow="Portfolio" title="Overview" description={<>KPIs, activity and health across tracked repositories. Window: last {filters.days} days.</>}
        actions={<FilterBar />} />
      {data && <DataModeBanner mode={data.data_mode} />}
      {error ? <Card><ErrorState error={error} onRetry={() => refetch()} /></Card> : null}
      {isLoading && <Loading rows={6} />}
      {data && k && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <KpiCard index={0} label="Repositories" value={num(k.repositories)} icon={Activity} hint={`${k.contributors_total} contributors`} accent="cyan" />
            <KpiCard index={1} label="Stars" value={compact(k.stars_total)} hint={`+${num(k.stars_gained_window)} in window`} icon={Star} accent="amber" />
            <KpiCard index={2} label="Commits" value={num(k.commits_window)} delta={k.commit_change_pct} hint="vs previous window" icon={GitCommit} accent="cyan" />
            <KpiCard index={3} label="PRs merged" value={num(k.prs_merged_window)} hint={`${num(k.open_prs)} open`} icon={GitMerge} accent="violet" />
            <KpiCard index={4} label="Median merge" value={hours(k.median_merge_hours)} hint="PR cycle time" icon={Timer} accent="emerald" />
            <KpiCard index={5} label="Open issues" value={num(k.open_issues)} hint={`${num(k.issues_closed_window)} closed`} icon={CircleDot} accent="rose" />
            <KpiCard index={6} label="Avg health" value={k.avg_health_score === null ? "–" : k.avg_health_score.toFixed(1)} hint="0–100 weighted score" icon={GitPullRequest} accent="emerald" />
            <KpiCard index={7} label="Anomalies (14d)" value={num(k.anomalies_last_14_days)} hint="robust z-score alerts" icon={AlertTriangle} accent="amber" />
          </div>

          {data.data_mode.mode === "empty" ? (
            <Card><EmptyState title="No repository data yet" body="Add a repository on the Pipelines page and run the ELT pipeline, or seed the labelled demo dataset as an admin." action={<Link to="/pipelines" className="text-sm text-cyan-300 hover:underline">Open Pipelines →</Link>} /></Card>
          ) : (
            <div className="grid gap-4 xl:grid-cols-3">
              <Card className="xl:col-span-2">
                <CardHeader title="Activity timeline" subtitle="Daily commits, merged PRs and closed issues (zero-filled)" />
                <div className="p-5 pt-3"><ActivityTimeline data={data.timeline} /></div>
              </Card>
              <Card>
                <CardHeader title="Language distribution" subtitle="Share of code bytes across repositories" />
                <div className="p-5 pt-3">{data.languages.length ? <LanguageDonut items={data.languages} /> : <EmptyState title="No language data" />}</div>
              </Card>
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Repository leaderboard" subtitle="Ranked by commits in the window" action={<Link to="/repos" className="text-xs text-cyan-300 hover:underline">All repositories →</Link>} />
              <div className="overflow-x-auto p-5 pt-3">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500">
                    <tr><th className="py-2">#</th><th>Repository</th><th className="text-right">Stars</th><th className="text-right">Commits</th><th className="text-right">PRs merged</th><th className="text-right">Health</th></tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {data.leaderboard.map((r, i) => (
                      <motion.tr key={r.repo_full_name} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }} className="hover:bg-white/[0.03]">
                        <td className="py-2.5 text-slate-500">{i + 1}</td>
                        <td className="py-2.5">
                          <Link to={`/repos/${r.repo_full_name}`} className="font-medium text-slate-100 hover:text-cyan-300">{r.repo_full_name}</Link>
                          <span className="ml-2 align-middle"><DataSourceBadge source={r.data_source} /></span>
                          <div className="text-xs text-slate-500">{r.language ?? "Unknown language"}</div>
                        </td>
                        <td className="text-right tabular-nums text-slate-300">{compact(r.stars)}</td>
                        <td className="text-right tabular-nums text-slate-200">{num(r.commits_window)}</td>
                        <td className="text-right tabular-nums text-slate-300">{num(r.prs_merged_window)}</td>
                        <td className="text-right"><span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${gradeColor(r.grade)}`}>{r.health_score.toFixed(0)} · {r.grade}</span></td>
                      </motion.tr>
                    ))}
                    {data.leaderboard.length === 0 && <tr><td colSpan={6}><EmptyState title="No repositories match these filters" /></td></tr>}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card>
              <CardHeader title="Health distribution" subtitle="Repositories per grade (A best → E worst)" />
              <div className="space-y-2.5 p-5 pt-3">
                {Object.entries(data.health_distribution).map(([g, n]) => {
                  const total = Object.values(data.health_distribution).reduce((a, b) => a + b, 0) || 1;
                  return (
                    <div key={g} className="flex items-center gap-3 text-sm">
                      <span className={`w-8 rounded-md border py-0.5 text-center text-xs font-bold ${gradeColor(g)}`}>{g}</span>
                      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/5">
                        <motion.div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-500" initial={{ width: 0 }} animate={{ width: `${(n / total) * 100}%` }} transition={{ duration: 0.6 }} />
                      </div>
                      <span className="w-6 text-right tabular-nums text-slate-400">{n}</span>
                    </div>
                  );
                })}
              </div>
              <div className="border-t border-white/10 p-5">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Recent anomalies</p>
                {data.recent_anomalies.length === 0 && <p className="text-sm text-slate-500">No unusual spikes or declines in the last 14 days.</p>}
                <ul className="space-y-2">
                  {data.recent_anomalies.slice(0, 5).map((a) => (
                    <li key={`${a.repo_full_name}-${a.date}`} className="flex items-start gap-2 text-sm">
                      <span className={`mt-0.5 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${severityColor(a.severity)}`}>{a.severity}</span>
                      <span className="min-w-0 text-slate-300"><span className="block truncate">{a.type.replace("_", " ")} · {a.date}</span>
                        <Link to={`/repos/${a.repo_full_name}`} className="block truncate text-xs text-slate-500 hover:text-cyan-300">{a.repo_full_name}</Link></span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          </div>
          <Panel className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
            <Badge tone="cyan">Analytics</Badge>
            <span>Forecasts, change points, PR cycle time and issue aging live on the </span>
            <Link to="/analytics" className="text-cyan-300 hover:underline">Analytics</Link>
            <span>page; natural-language questions go to the </span>
            <Link to="/assistant" className="text-cyan-300 hover:underline">AI Assistant</Link>.
            <span className="ml-auto text-xs text-slate-600">Generated {data.generated_at.slice(0, 16).replace("T", " ")} UTC · {signedPct(k.commit_change_pct)} commit change</span>
          </Panel>
        </>
      )}
    </>
  );
}
