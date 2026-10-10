import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowLeft, Download, ExternalLink, GitCommit, GitPullRequest, Users, Activity, CircleDot, LineChart, Flame } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Card, CardHeader, Select, Tabs } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { DataModeBanner, DataSourceBadge, EmptyState, ErrorState, Loading, PageHeader, Panel, Stat } from "@/components/common/common";
import { KpiCard } from "@/components/common/KpiCard";
import { ActivityTimeline, CalendarHeatmap, CorrelationTable, ForecastChart, Histogram, LanguageDonut, WeekdayBars, WeekdayHourHeatmap, MultiLine } from "@/components/charts/charts";
import { api, downloadExport } from "@/lib/api";
import { compact, dateLabel, gradeColor, hours, num, pct, signedPct, timeAgo } from "@/lib/format";
import { DAY_OPTIONS, useGlobalFilters } from "@/lib/filters";
import type { CommitRow, ContributorRow, Health, IssueRow, Page, PullRow, RepoAnalysis, RepoSummary, TimeseriesRow, TimelinePoint, LanguageRow, Insight, Anomaly } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RepoDetail {
  summary: RepoSummary;
  health: { score: number; grade: string; confidence: string; components: Health["components"]; weakest_component: string; data_gaps: string[]; method: string };
  languages: LanguageRow[];
  releases: { tag_name: string; name: string | null; published_at: string | null; prerelease: boolean }[];
  data_source: "github" | "synthetic";
  is_synthetic: boolean;
}

type Tab = "overview" | "analytics" | "commits" | "issues" | "contributors" | "activity";

export default function RepoDetailPage() {
  const { owner = "", name = "" } = useParams();
  const fn = `${owner}/${name}`;
  const { filters, setFilter } = useGlobalFilters();
  const [tab, setTab] = useState<Tab>("overview");
  const days = filters.days;

  const detail = useQuery({
    queryKey: ["repo", fn, days],
    queryFn: ({ signal }) => api.get<RepoDetail>(`/repos/${owner}/${name}?days=${days}`, signal),
    retry: (n, err: any) => (err?.status === 404 ? false : n < 2),
  });

  if (detail.isLoading) return <Loading rows={6} />;
  if (detail.error) return <Card><ErrorState error={detail.error} onRetry={() => detail.refetch()} /></Card>;
  const d = detail.data!;
  const s = d.summary;
  const dataMode = { mode: d.is_synthetic ? "synthetic" as const : "live" as const, github_repos: d.is_synthetic ? 0 : 1, synthetic_repos: d.is_synthetic ? 1 : 0 };

  return (
    <>
      <Link to="/repos" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-cyan-300"><ArrowLeft className="h-3.5 w-3.5" /> All repositories</Link>
      <PageHeader eyebrow={s.owner} title={s.name}
        description={<span className="flex flex-wrap items-center gap-2">{s.language ?? "Unknown language"} · pushed {timeAgo(s.pushed_at)} · <DataSourceBadge source={d.data_source} />
          {s.is_private && <Badge tone="amber">private</Badge>}</span>}
        actions={<>
          <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/commits?repo=${encodeURIComponent(fn)}&days=${days}&format=csv`, `${name}-commits.csv`)}><Download className="h-4 w-4" /> Commits CSV</Button>
          <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/daily?repo=${encodeURIComponent(fn)}&days=${days}&format=json`, `${name}-daily.json`)}><Download className="h-4 w-4" /> Daily JSON</Button>
          <a href={`https://github.com/${fn}`} target="_blank" rel="noreferrer" className="inline-flex"><Button variant="ghost" size="sm"><ExternalLink className="h-4 w-4" /> GitHub</Button></a>
        </>} />
      <DataModeBanner mode={dataMode} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs<Tab> value={tab} onChange={setTab} items={[
          { id: "overview", label: "Overview", icon: <Activity className="h-3.5 w-3.5" /> },
          { id: "analytics", label: "Analytics & forecast", icon: <LineChart className="h-3.5 w-3.5" /> },
          { id: "commits", label: "Commits", icon: <GitCommit className="h-3.5 w-3.5" /> },
          { id: "issues", label: "Issues & PRs", icon: <CircleDot className="h-3.5 w-3.5" /> },
          { id: "contributors", label: "Contributors", icon: <Users className="h-3.5 w-3.5" /> },
          { id: "activity", label: "Activity", icon: <Flame className="h-3.5 w-3.5" /> },
        ]} />
        <Select aria-label="Window" value={days} onChange={(e) => setFilter("days", e.target.value)} className="w-44">
          {DAY_OPTIONS.map((o) => <option key={o} value={o} className="bg-ink-900">Last {o} days</option>)}
        </Select>
      </div>

      <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className="grid gap-4">
        {tab === "overview" && <OverviewTab fn={fn} d={d} days={days} />}
        {tab === "analytics" && <AnalyticsTab owner={owner} name={name} days={days} />}
        {tab === "commits" && <CommitsTab fn={fn} days={days} />}
        {tab === "issues" && <IssuesTab fn={fn} />}
        {tab === "contributors" && <ContributorsTab fn={fn} />}
        {tab === "activity" && <ActivityTab fn={fn} days={days} />}
      </motion.div>
    </>
  );
}

function OverviewTab({ fn, d, days }: { fn: string; d: RepoDetail; days: number }) {
  const s = d.summary;
  const [owner, name] = fn.split("/");
  const ts = useQuery({
    queryKey: ["repo-ts", fn, days],
    queryFn: ({ signal }) => api.get<{ items: TimeseriesRow[] }>(`/repos/${owner}/${name}/timeseries?days=${Math.min(Math.max(days, 7), 730)}`, signal),
  });
  const timeline: TimelinePoint[] = (ts.data?.items ?? []).map((r) => ({
    date: r.activity_date, commits: r.commits, issues_opened: r.issues_opened, issues_closed: r.issues_closed,
    prs_opened: r.prs_opened, prs_merged: r.prs_merged, stars_gained: r.stars_gained,
  }));
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard index={0} label="Stars" value={compact(s.stars)} hint={`+${num(s.stars_gained_window)} in window`} icon={Activity} accent="amber" />
        <KpiCard index={1} label="Commits (window)" value={num(s.commits_window)} hint={`${num(s.commits_30d)} in 30d · ${num(s.commit_authors)} authors`} icon={GitCommit} accent="cyan" />
        <KpiCard index={2} label="PRs merged" value={num(s.prs_merged_window)} hint={`${num(s.prs_open)} open · median ${hours(s.median_merge_hours)}`} icon={GitPullRequest} accent="violet" />
        <KpiCard index={3} label="Health" value={d.health.score.toFixed(1)} hint={`grade ${d.health.grade} · ${d.health.confidence} confidence`} icon={Activity} accent="emerald" />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Daily activity" subtitle="Commits, PRs and issues per day" />
          <div className="p-5 pt-3">{timeline.length ? <ActivityTimeline data={timeline} height={260} /> : <EmptyState title="No activity in this window" />}</div>
        </Card>
        <Card>
          <CardHeader title="Languages" subtitle="Share of code bytes" />
          <div className="p-5 pt-3">{d.languages.length ? <LanguageDonut items={d.languages} /> : <EmptyState title="No language data" />}</div>
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Health score breakdown" subtitle={`Method: ${d.health.method}`} />
          <div className="space-y-3 p-5 pt-3">
            <div className="flex items-center gap-3">
              <span className={cn("rounded-lg border px-3 py-1 text-lg font-bold", gradeColor(d.health.grade))}>{d.health.grade}</span>
              <span className="text-sm text-slate-400">Weakest: <span className="text-slate-200">{d.health.weakest_component.replace(/_/g, " ")}</span></span>
            </div>
            {Object.entries(d.health.components).map(([k, c]) => (
              <div key={k} title={c.explanation}>
                <div className="mb-1 flex justify-between text-xs text-slate-400"><span className="capitalize">{k.replace(/_/g, " ")}</span><span className="tabular-nums">{c.raw === null ? "no data" : `${c.score.toFixed(0)} · weight ${(c.weight * 100).toFixed(0)}%`}</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-white/5"><motion.div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400" initial={{ width: 0 }} animate={{ width: `${c.score}%` }} transition={{ duration: 0.6 }} /></div>
                <p className="mt-1 text-[11px] text-slate-500">{c.explanation}</p>
              </div>
            ))}
            {d.health.data_gaps.length > 0 && <p className="rounded-lg bg-amber-400/5 p-2 text-xs text-amber-200">Data gaps: {d.health.data_gaps.join("; ")}</p>}
          </div>
        </Card>
        <Card>
          <CardHeader title="Releases" subtitle={`${num(s.releases_count)} total`} />
          <div className="p-5 pt-3">
            {d.releases.length === 0 ? <EmptyState title="No releases recorded" body="Releases appear once they are published on GitHub." /> :
              <ul className="divide-y divide-white/5">{d.releases.slice(0, 8).map((r) => (
                <li key={r.tag_name} className="flex items-center justify-between py-2 text-sm">
                  <span className="truncate text-slate-200">{r.tag_name}{r.prerelease && <Badge className="ml-2" tone="amber">pre</Badge>}</span>
                  <span className="shrink-0 text-xs text-slate-500">{dateLabel(r.published_at)}</span>
                </li>))}</ul>}
          </div>
        </Card>
      </div>
    </>
  );
}

function AnalyticsTab({ owner, name, days }: { owner: string; name: string; days: number }) {
  const [metric, setMetric] = useState<"commits" | "stars" | "issues_opened" | "prs_merged">("commits");
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["repo-analysis", owner, name, days, metric],
    queryFn: ({ signal }) => api.get<RepoAnalysis>(`/analytics/repos/${owner}/${name}?days=${Math.max(days, 14)}&metric=${metric}`, signal),
  });
  if (isLoading) return <Loading rows={5} />;
  if (error) return <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>;
  if (!data) return null;
  const f = data.forecast;
  return (
    <>
      <Panel className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-400">Metric</span>
        <Select aria-label="Metric" value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)} className="w-44">
          <option value="commits" className="bg-ink-900">Commits</option>
          <option value="stars" className="bg-ink-900">Stars gained</option>
          <option value="issues_opened" className="bg-ink-900">Issues opened</option>
          <option value="prs_merged" className="bg-ink-900">PRs merged</option>
        </Select>
        <Badge tone={data.is_synthetic ? "violet" : "emerald"}>{data.is_synthetic ? "DEMO · synthetic" : "live GitHub data"}</Badge>
        <span className="ml-auto text-xs text-slate-500">Observations are solid lines; predictions are dashed and shaded by interval.</span>
      </Panel>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Mean / day" value={num(data.descriptive?.mean, 2)} hint={`median ${num(data.descriptive?.median, 2)}`} />
        <Stat label="Trend" value={data.trend.direction ?? data.trend.status} hint={data.trend.pct_change_over_window !== undefined ? `${signedPct(data.trend.pct_change_over_window)} over window` : data.trend.reason} tone={data.trend.direction === "up" ? "good" : data.trend.direction === "down" ? "bad" : "neutral"} />
        <Stat label="Seasonality" value={data.seasonality.status === "ok" ? `${data.seasonality.peak_day ?? "–"} peak` : "not detected"} hint={data.seasonality.interpretation ?? data.seasonality.reason} />
        <Stat label="Forecast" value={f.status === "ok" ? `${f.reliability ?? ""} reliability` : "insufficient data"} hint={f.status === "ok" ? `${f.horizon_days}-day horizon · ${f.model}` : f.reason} />
      </div>

      <Card>
        <CardHeader title="Observed history and forecast" subtitle={f.status === "ok" ? `${f.history_points} observed days · ${f.model}` : "Forecast withheld"} />
        <div className="p-5 pt-3">
          {f.status === "ok" ? (
            <>
              <ForecastChart forecast={f} />
              {f.evaluation && (
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                  <Stat label="Backtest MAE" value={num(f.evaluation.model_mae, 2)} hint={`${f.evaluation.holdout_days}-day holdout`} />
                  <Stat label="RMSE" value={num(f.evaluation.model_rmse, 2)} />
                  <Stat label="MAPE" value={f.evaluation.model_mape_pct === null ? "n/a" : `${f.evaluation.model_mape_pct.toFixed(1)}%`} />
                  <Stat label="80% interval coverage" value={f.evaluation.interval_coverage_80 === null ? "n/a" : pct(f.evaluation.interval_coverage_80 * 100, 0)} hint={`baseline ${f.evaluation.baseline} MAE ${num(f.evaluation.baseline_mae, 2)}`} />
                </div>
              )}
              <p className="mt-3 text-xs text-slate-500">{f.disclaimer}</p>
            </>
          ) : <EmptyState title="Forecast withheld" body={f.reason ?? "Not enough history for a reliable forecast."} />}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Weekday profile" subtitle={data.seasonality.interpretation ?? "Average activity per weekday"} />
          <div className="p-5 pt-3">{data.seasonality.weekday_profile ? <WeekdayBars profile={data.seasonality.weekday_profile} /> : <EmptyState title="Seasonality not assessed" body={data.seasonality.reason} />}</div>
        </Card>
        <Card>
          <CardHeader title="Change points" subtitle={data.changepoints.status === "ok" ? "Level shifts (Welch t-test binary segmentation)" : "Change-point detection"} />
          <div className="p-5 pt-3">
            {data.changepoints.status === "ok" && data.changepoints.changepoints.length ? (
              <ul className="space-y-2">{data.changepoints.changepoints.map((c) => (
                <li key={c.date} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm">
                  <span className="text-slate-200">{c.date}</span>
                  <span className="tabular-nums text-slate-400">{num(c.mean_before, 2)} → {num(c.mean_after, 2)} <span className={c.direction === "increase" ? "text-emerald-300" : "text-rose-300"}>({c.relative_change_pct === null ? "n/a" : signedPct(c.relative_change_pct)})</span></span>
                </li>))}</ul>
            ) : <EmptyState title="No significant level shifts" body={data.changepoints.reason ?? "No change point passed the significance threshold."} />}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Moving averages" subtitle="7-day and 28-day smoothing of the observed series" />
          <div className="p-5 pt-3"><MultiLine data={data.moving_averages.map((m) => ({ date: m.date, value: m.value, ma7: m.ma7, ma28: m.ma28 }))} xKey="date"
            lines={[{ key: "value", name: "Daily", color: "#64748b" }, { key: "ma7", name: "MA 7", color: "#22d3ee" }, { key: "ma28", name: "MA 28", color: "#a78bfa" }]} /></div>
        </Card>
        <Card>
          <CardHeader title="Anomalies" subtitle={data.anomalies.method ? `Method: ${data.anomalies.method}` : "Robust z-score scan"} />
          <div className="space-y-2 p-5 pt-3">
            {data.anomalies.anomalies.length === 0 && <EmptyState title="No anomalies" body={data.anomalies.reason ?? "No day departed strongly from its robust baseline."} />}
            {data.anomalies.anomalies.slice(0, 6).map((a: Anomaly) => (
              <div key={a.date} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5 text-xs">
                <div className="flex justify-between"><span className="font-medium text-slate-200">{a.date} · {a.type.replace("_", " ")}</span><span className="text-slate-400">z {a.z_score.toFixed(1)}</span></div>
                <p className="mt-1 text-slate-500">{a.explanation}</p>
              </div>))}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Correlation" subtitle={data.correlation.status === "ok" ? "Association between daily metrics — not causation" : "Correlation analysis"} />
          <div className="p-5 pt-3">{data.correlation.status === "ok" && data.correlation.pairs.length ? <CorrelationTable pairs={data.correlation.pairs} /> : <EmptyState title="Correlation not computed" body={data.correlation.reason} />}</div>
        </Card>
        <Card>
          <CardHeader title="Contributor concentration" subtitle={data.contributor_patterns.status === "ok" ? data.contributor_patterns.pattern : "Contributor patterns"} />
          <div className="space-y-3 p-5 pt-3 text-sm">
            {data.contributor_patterns.status === "ok" ? <>
              <Stat label="Top contributor share" value={`${(data.contributor_patterns.top_share_pct ?? 0).toFixed(1)}%`} hint={data.contributor_patterns.top_contributor} />
              <div className="grid grid-cols-3 gap-3"><Stat label="Gini" value={num(data.contributor_patterns.gini, 2)} /><Stat label="Bus factor (50%)" value={num(data.contributor_patterns.bus_factor_50pct)} /><Stat label="Contributors" value={num(data.contributor_patterns.contributors)} /></div>
              <p className="text-xs text-slate-500">{data.contributor_patterns.interpretation}</p>
            </> : <EmptyState title="Not enough contributor data" body={data.contributor_patterns.reason} />}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Explainable insights" subtitle="Each finding lists its evidence and the mart it was computed from" />
        <div className="grid gap-3 p-5 pt-3 md:grid-cols-2">
          {data.insights.length === 0 && <EmptyState title="No findings" body="The data did not support any finding above the noise threshold." />}
          {data.insights.map((i: Insight) => <InsightCard key={i.id} i={i} />)}
        </div>
      </Card>
    </>
  );
}

export function InsightCard({ i }: { i: Insight }) {
  const tone = i.severity === "high" ? "rose" : i.severity === "medium" ? "amber" : i.severity === "info" ? "sky" : "neutral";
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge tone={tone as "rose"}>{i.severity}</Badge>
        <Badge>{i.category}</Badge>
        {i.repo_full_name && <span className="text-[11px] text-slate-500">{i.repo_full_name}</span>}
      </div>
      <h4 className="text-sm font-semibold text-slate-100">{i.title}</h4>
      <p className="mt-1 text-xs text-slate-400">{i.evidence}</p>
      <p className="mt-2 text-xs text-cyan-200/80">→ {i.recommendation}</p>
      <p className="mt-2 text-[10px] uppercase tracking-wider text-slate-600">source: {i.source.join(", ")}</p>
    </div>
  );
}

function CommitsTab({ fn, days }: { fn: string; days: number }) {
  const [page, setPage] = useState(1);
  const [owner, name] = fn.split("/");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["repo-commits", fn, days, page],
    queryFn: ({ signal }) => api.get<Page<CommitRow>>(`/repos/${owner}/${name}/commits?days=${Math.min(days, 3650)}&page=${page}&page_size=25`, signal),
    placeholderData: (prev) => prev,
  });
  return (
    <Card>
      <CardHeader title="Commits" subtitle={data ? `${num(data.total)} in window · page ${data.page}` : "Loading"} action={
        <div className="flex gap-2"><Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
          <Button variant="ghost" size="sm" disabled={!data || page * 25 >= data.total} onClick={() => setPage((p) => p + 1)}>Next</Button></div>} />
      <div className="overflow-x-auto p-5 pt-3">
        {isLoading ? <Loading rows={5} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data?.items.length ? <EmptyState title="No commits in this window" /> :
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">SHA</th><th>Message</th><th>Author</th><th className="text-right">When</th></tr></thead>
            <tbody className="divide-y divide-white/5">{data.items.map((c) => (
              <tr key={c.sha} className="hover:bg-white/[0.03]">
                <td className="py-2 font-mono text-xs text-cyan-300">{c.sha.slice(0, 7)}</td>
                <td className="max-w-[420px] truncate py-2 text-slate-200" title={c.message_headline}>{c.message_headline}</td>
                <td className="py-2 text-slate-400">{c.author_login ?? c.author_name ?? "unknown"}</td>
                <td className="py-2 text-right text-xs text-slate-500">{dateLabel(c.committed_at)}</td>
              </tr>))}</tbody>
          </table>}
      </div>
    </Card>
  );
}

function IssuesTab({ fn }: { fn: string }) {
  const [owner, name] = fn.split("/");
  const [state, setState] = useState<"open" | "closed" | "all">("open");
  const issues = useQuery({ queryKey: ["repo-issues", fn, state], queryFn: ({ signal }) => api.get<Page<IssueRow>>(`/repos/${owner}/${name}/issues?state=${state}&page_size=25`, signal) });
  const pulls = useQuery({ queryKey: ["repo-pulls", fn, state], queryFn: ({ signal }) => api.get<Page<PullRow>>(`/repos/${owner}/${name}/pulls?state=${state}&page_size=25`, signal) });
  return (
    <>
      <Panel className="flex items-center gap-3 text-sm"><span className="text-slate-400">State</span>
        <Select aria-label="State" value={state} onChange={(e) => setState(e.target.value as typeof state)} className="w-40">
          <option value="open" className="bg-ink-900">Open</option><option value="closed" className="bg-ink-900">Closed</option><option value="all" className="bg-ink-900">All</option>
        </Select></Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Issues" subtitle={issues.data ? `${num(issues.data.total)} matching` : ""} />
          <div className="overflow-x-auto p-5 pt-3">
            {issues.isLoading ? <Loading rows={4} /> : !issues.data?.items.length ? <EmptyState title="No issues" /> :
              <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">#</th><th>Title</th><th className="text-right">Age / close</th></tr></thead>
                <tbody className="divide-y divide-white/5">{issues.data.items.map((i) => (
                  <tr key={i.number}><td className="py-2 text-slate-500">#{i.number}</td><td className="max-w-[260px] truncate py-2 text-slate-200" title={i.title}>{i.title}</td>
                    <td className="py-2 text-right text-xs text-slate-400">{i.state === "open" ? `${num(i.open_age_days)} d open` : `closed in ${hours(i.close_hours)}`}</td></tr>))}</tbody></table>}
          </div>
        </Card>
        <Card>
          <CardHeader title="Pull requests" subtitle={pulls.data ? `${num(pulls.data.total)} matching` : ""} />
          <div className="overflow-x-auto p-5 pt-3">
            {pulls.isLoading ? <Loading rows={4} /> : !pulls.data?.items.length ? <EmptyState title="No pull requests" /> :
              <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">#</th><th>Title</th><th className="text-right">Status</th></tr></thead>
                <tbody className="divide-y divide-white/5">{pulls.data.items.map((p) => (
                  <tr key={p.number}><td className="py-2 text-slate-500">#{p.number}</td><td className="max-w-[260px] truncate py-2 text-slate-200" title={p.title}>{p.title}{p.is_draft && <Badge className="ml-2">draft</Badge>}</td>
                    <td className="py-2 text-right text-xs text-slate-400">{p.merged_at ? `merged · ${hours(p.merge_hours)}` : p.state}</td></tr>))}</tbody></table>}
          </div>
        </Card>
      </div>
    </>
  );
}

function ContributorsTab({ fn }: { fn: string }) {
  const [owner, name] = fn.split("/");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["repo-contributors", fn],
    queryFn: ({ signal }) => api.get<{ items: ContributorRow[] }>(`/repos/${owner}/${name}/contributors`, signal),
  });
  return (
    <Card>
      <CardHeader title="Contributors" subtitle="Ranked by commit share in this repository" />
      <div className="overflow-x-auto p-5 pt-3">
        {isLoading ? <Loading rows={5} /> : error ? <ErrorState error={error} onRetry={() => refetch()} /> : !data?.items.length ? <EmptyState title="No contributors recorded" /> :
          <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">#</th><th>Login</th><th className="text-right">Commits</th><th className="text-right">30d</th><th className="text-right">Share</th><th className="text-right">Last commit</th></tr></thead>
            <tbody className="divide-y divide-white/5">{data.items.map((c) => (
              <tr key={c.login} className="hover:bg-white/[0.03]">
                <td className="py-2 text-slate-500">{c.rank_in_repo}</td>
                <td className="py-2"><Link to={`/contributors?login=${encodeURIComponent(c.login)}`} className="text-slate-100 hover:text-cyan-300">@{c.login}</Link></td>
                <td className="text-right tabular-nums">{num(c.commits_total)}</td><td className="text-right tabular-nums text-slate-400">{num(c.commits_30d)}</td>
                <td className="text-right tabular-nums text-slate-400">{pct((c.share_of_commits ?? 0) * 100)}</td>
                <td className="text-right text-xs text-slate-500">{timeAgo(c.last_commit_at)}</td></tr>))}</tbody></table>}
      </div>
    </Card>
  );
}

function ActivityTab({ fn, days }: { fn: string; days: number }) {
  const [owner, name] = fn.split("/");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["repo-heatmap", fn, days],
    queryFn: ({ signal }) => api.get<{ weekday_hour: { weekday: number; hour_utc: number; commits: number }[]; daily: { date: string; commits: number }[] }>(`/repos/${owner}/${name}/heatmap?days=${Math.max(days, 7)}`, signal),
  });
  if (isLoading) return <Loading rows={3} />;
  if (error) return <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>;
  if (!data) return null;
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card><CardHeader title="Calendar" subtitle={`Commits per day, last ${days} days`} /><div className="p-5 pt-3"><CalendarHeatmap data={data.daily} days={Math.min(days, 365)} /></div></Card>
        <Card><CardHeader title="When work happens" subtitle="Commits by weekday and hour (UTC)" /><div className="p-5 pt-3"><WeekdayHourHeatmap data={data.weekday_hour} /></div></Card>
      </div>
      <Card><CardHeader title="Commit-count distribution" subtitle="Histogram of daily commit counts" />
        <div className="p-5 pt-3"><Histogram data={histogram(data.daily.map((d) => d.commits))} /></div></Card>
    </>
  );
}

function histogram(values: number[]) {
  const buckets = ["0", "1", "2–3", "4–6", "7–10", "11+"];
  const counts = [0, 0, 0, 0, 0, 0];
  values.forEach((v) => {
    const i = v === 0 ? 0 : v === 1 ? 1 : v <= 3 ? 2 : v <= 6 ? 3 : v <= 10 ? 4 : 5;
    counts[i] += 1;
  });
  return buckets.map((b, i) => ({ bucket: b, count: counts[i] }));
}
