import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, CardHeader, Tabs } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Loading, PageHeader, Stat, DataSourceBadge, Panel } from "@/components/common/common";
import { FilterBar } from "@/components/common/FilterBar";
import { Histogram, MultiLine } from "@/components/charts/charts";
import { InsightCard } from "./RepoDetailPage";
import { api, downloadExport } from "@/lib/api";
import { gradeColor, hours, num } from "@/lib/format";
import { useGlobalFilters } from "@/lib/filters";
import { cn } from "@/lib/utils";
import type { AnomalyResponse, HealthItem, Insight, IssueAging, PortfolioInsights, PrCycle } from "@/lib/types";
import { Download, GitMerge, ShieldAlert, Sparkles, HeartPulse, Layers, Timer } from "lucide-react";
import { motion } from "framer-motion";

type Section = "portfolio" | "delivery" | "health" | "anomalies" | "insights";

export default function AnalyticsPage() {
  const [section, setSection] = useState<Section>("portfolio");
  const { filters } = useGlobalFilters();
  const days = filters.days;
  return (
    <>
      <PageHeader eyebrow="Analytics" title="Analytics"
        description="Descriptive, diagnostic and predictive views across the portfolio. Each finding names its evidence and whether it is an observation or a model estimate."
        actions={<FilterBar showSource={false} />} />
      <Tabs<Section> value={section} onChange={setSection} items={[
        { id: "portfolio", label: "Portfolio", icon: <Layers className="h-3.5 w-3.5" /> },
        { id: "delivery", label: "Delivery", icon: <Timer className="h-3.5 w-3.5" /> },
        { id: "health", label: "Health", icon: <HeartPulse className="h-3.5 w-3.5" /> },
        { id: "anomalies", label: "Anomalies", icon: <ShieldAlert className="h-3.5 w-3.5" /> },
        { id: "insights", label: "Insights", icon: <Sparkles className="h-3.5 w-3.5" /> },
      ]} />
      <motion.div key={section} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className="grid gap-4">
        {section === "portfolio" && <PortfolioSection days={days} />}
        {section === "delivery" && <DeliverySection days={days} />}
        {section === "health" && <HealthSection days={days} />}
        {section === "anomalies" && <AnomalySection />}
        {section === "insights" && <InsightsSection />}
      </motion.div>
    </>
  );
}

function Query<T,>({ k, path, children }: { k: unknown[]; path: string; children: (d: T) => ReactNode }) {
  const q = useQuery({ queryKey: k, queryFn: ({ signal }) => api.get<T>(path, signal) });
  if (q.isLoading) return <Loading rows={4} />;
  if (q.error) return <Card><ErrorState error={q.error} onRetry={() => q.refetch()} /></Card>;
  return q.data ? <>{children(q.data)}</> : null;
}

function PortfolioSection({ days }: { days: number }) {
  return (
    <Query<PortfolioInsights> k={["portfolio", days]} path={`/analytics/portfolio?days=${Math.max(days, 7)}`}>{(p) => (
      <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Repositories analysed" value={num(p.repos)} />
          <Stat label="Low health" value={num(p.low_health.length)} hint={p.low_health.slice(0, 2).join(", ") || "none"} tone={p.low_health.length ? "bad" : "good"} />
          <Stat label="Stale" value={num(p.stale.length)} hint={p.stale.slice(0, 2).join(", ") || "none"} tone={p.stale.length ? "bad" : "neutral"} />
          <Stat label="Outliers" value={num(p.outliers.outliers.length)} hint={p.outliers.method} />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader title="Outliers (Tukey IQR)" subtitle="Repositories outside the fence on log-scaled metrics" />
            <div className="space-y-2 p-5 pt-3">
              {p.outliers.outliers.length === 0 ? <EmptyState title="No outliers" body="No repository sits outside the interquartile fence." /> :
                p.outliers.outliers.map((o, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm">
                    <Link className="text-slate-200 hover:text-cyan-300" to={`/repos/${o.repo_full_name}`}>{o.repo_full_name}</Link>
                    <span className="text-xs text-slate-400"><Badge tone={o.direction === "high" ? "amber" : "rose"}>{o.direction}</Badge> <span className="ml-1 tabular-nums">{o.metric.replace(/_/g, " ")} = {num(o.value)}</span></span>
                  </div>))}
            </div>
          </Card>
          <Card>
            <CardHeader title="Activity clusters" subtitle="Similar activity profiles — not quality rankings" />
            <div className="space-y-3 p-5 pt-3">
              {p.clusters.status !== "ok" ? <EmptyState title="Clustering withheld" body={p.clusters.reason ?? "Not enough repositories for guarded clustering."} /> : <>
                <p className="text-xs text-slate-500">k = {p.clusters.k} on {p.clusters.features?.join(", ").replace(/_/g, " ")}</p>
                {p.clusters.clusters?.map((c) => (
                  <div key={c.cluster} className="rounded-lg border border-white/10 p-3">
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Cluster {c.cluster + 1} · {c.size} repo(s)</div>
                    <div className="flex flex-wrap gap-1.5">{c.repos.map((r) => <Link key={r} to={`/repos/${r}`}><Badge tone="cyan" className="hover:bg-cyan-400/20">{r}</Badge></Link>)}</div>
                  </div>))}
                {p.clusters.note && <p className="text-xs text-slate-500">{p.clusters.note}</p>}
              </>}
            </div>
          </Card>
        </div>
      </>)}</Query>
  );
}

function DeliverySection({ days }: { days: number }) {
  const [repo, setRepo] = useState("");
  const repoParam = repo ? `&repo=${encodeURIComponent(repo)}` : "";
  return (
    <>
      <Panel className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
        <GitMerge className="h-4 w-4 text-violet-300" /> PR cycle time and issue aging. Leave the repository blank for the whole portfolio.
        <RepoInput value={repo} onChange={setRepo} />
      </Panel>
      <Query<PrCycle> k={["pr-cycle", days, repo]} path={`/analytics/pr-cycle?days=${Math.max(days, 7)}${repoParam}`}>{(p) => (
        <Card>
          <CardHeader title="Pull request cycle time" subtitle={`${num(p.distribution.count)} merged PRs · last ${p.days} days`} action={
            <Button variant="outline" size="sm" onClick={() => downloadExport(`/exports/pulls?days=${p.days}&format=csv${repoParam}`, "pulls.csv")}><Download className="h-4 w-4" /> Pulls CSV</Button>} />
          <div className="grid gap-4 p-5 pt-3 xl:grid-cols-3">
            <div className="grid grid-cols-2 gap-3 content-start">
              <Stat label="Median" value={hours(p.distribution.median_hours)} />
              <Stat label="P90" value={hours(p.distribution.p90_hours)} />
              <Stat label="Merged within 24h" value={p.distribution.within_24h_pct === null ? "n/a" : `${p.distribution.within_24h_pct.toFixed(1)}%`} />
              <Stat label="Over 7 days" value={p.distribution.over_7d_pct === null ? "n/a" : `${p.distribution.over_7d_pct.toFixed(1)}%`} tone={(p.distribution.over_7d_pct ?? 0) > 20 ? "bad" : "neutral"} />
            </div>
            <div className="xl:col-span-2">
              {p.distribution.histogram.length ? <Histogram data={p.distribution.histogram} color="#a78bfa" /> : <EmptyState title="No merged PRs" />}
            </div>
            <div className="xl:col-span-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Weekly median merge time (hours)</p>
              {p.weekly.length ? <MultiLine xKey="week" data={p.weekly.map((w) => ({ week: w.week, median: w.median_merge_hours, p90: w.p90_merge_hours }))}
                lines={[{ key: "median", name: "Median", color: "#a78bfa" }, { key: "p90", name: "P90", color: "#f472b6" }]} height={220} /> : <EmptyState title="No weekly data" />}
            </div>
          </div>
        </Card>)}</Query>
      <Query<IssueAging> k={["issue-aging", repo]} path={`/analytics/issue-aging${repo ? `?repo=${encodeURIComponent(repo)}` : ""}`}>{(a) => (
        <Card>
          <CardHeader title="Issue aging" subtitle={`${num(a.open_issues)} open issues`} />
          <div className="grid gap-4 p-5 pt-3 xl:grid-cols-3">
            <div className="grid grid-cols-2 gap-3 content-start">
              <Stat label="Closed (all time)" value={num(a.resolution.closed_count)} />
              <Stat label="Median close" value={a.resolution.median_close_days === null ? "n/a" : `${a.resolution.median_close_days.toFixed(1)} d`} />
              <Stat label="P90 close" value={a.resolution.p90_close_days === null ? "n/a" : `${a.resolution.p90_close_days.toFixed(1)} d`} />
              <Stat label="Closed within 7 days" value={a.resolution.closed_within_7d_pct === null ? "n/a" : `${a.resolution.closed_within_7d_pct.toFixed(1)}%`} />
            </div>
            <div className="xl:col-span-2"><Histogram data={a.buckets.map((b) => ({ bucket: b.age_bucket, count: b.open_issues }))} color="#fbbf24" yName="Open issues" /></div>
          </div>
        </Card>)}</Query>
    </>
  );
}

function RepoInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input aria-label="Repository (owner/name)" value={value} onChange={(e) => onChange(e.target.value.trim())} placeholder="owner/name (optional)"
      className="h-9 w-64 rounded-xl border border-slate-600/50 bg-ink-900/70 px-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none" />
  );
}

function HealthSection({ days }: { days: number }) {
  return (
    <Query<{ items: HealthItem[]; method: string }> k={["health", days]} path={`/analytics/health?days=${Math.max(days, 7)}`}>{(h) => (
      <Card>
        <CardHeader title="Repository health" subtitle={h.method} />
        <div className="overflow-x-auto p-5 pt-3">
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">Repository</th><th className="text-right">Score</th><th>Weakest</th><th>Confidence</th><th>Data gaps</th></tr></thead>
            <tbody className="divide-y divide-white/5">{h.items.map((r) => (
              <tr key={r.repo_full_name}>
                <td className="py-2.5"><Link to={`/repos/${r.repo_full_name}`} className="text-slate-100 hover:text-cyan-300">{r.repo_full_name}</Link> <DataSourceBadge source={r.data_source} /></td>
                <td className="text-right"><span className={cn("rounded-md border px-2 py-0.5 text-xs font-semibold", gradeColor(r.grade))}>{r.score.toFixed(1)} · {r.grade}</span></td>
                <td className="text-slate-400">{r.weakest_component.replace(/_/g, " ")}</td>
                <td className="text-slate-400">{r.confidence}</td>
                <td className="max-w-[260px] truncate text-xs text-slate-500" title={r.data_gaps.join("; ")}>{r.data_gaps.length ? r.data_gaps.join("; ") : "none"}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Card>)}</Query>
  );
}

function AnomalySection() {
  const [days, setDays] = useState(90);
  return (
    <>
      <Panel className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
        Window
        {[30, 90, 180].map((d) => <Button key={d} size="sm" variant={days === d ? "default" : "ghost"} onClick={() => setDays(d)}>{d} days</Button>)}
        <span className="ml-auto text-xs">Robust z-score (median/MAD) with Isolation Forest corroboration where history allows.</span>
      </Panel>
      <Query<AnomalyResponse> k={["anomalies", days]} path={`/analytics/anomalies?days=${days}`}>{(a) => (
        <Card>
          <CardHeader title="Detected anomalies" subtitle={`${a.count} flagged · ${a.repos_scanned} repos scanned · ${a.repos_skipped_insufficient_history} skipped (insufficient history)`} />
          <div className="overflow-x-auto p-5 pt-3">
            {a.anomalies.length === 0 ? <EmptyState title="No anomalies in this window" body="Either nothing unusual happened or history was too short to judge." /> :
              <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">Date</th><th>Repository</th><th>Type</th><th className="text-right">Value / expected</th><th className="text-right">z</th><th>Severity</th></tr></thead>
                <tbody className="divide-y divide-white/5">{a.anomalies.map((x) => (
                  <tr key={`${x.repo_full_name}-${x.date}`}>
                    <td className="py-2 text-slate-300">{x.date}</td>
                    <td><Link to={`/repos/${x.repo_full_name}`} className="text-slate-200 hover:text-cyan-300">{x.repo_full_name}</Link></td>
                    <td className="text-slate-400">{x.type.replace("_", " ")}</td>
                    <td className="text-right tabular-nums">{num(x.value, 1)} / {x.expected === null ? "–" : num(x.expected, 1)}</td>
                    <td className="text-right tabular-nums text-slate-400">{x.z_score.toFixed(1)}</td>
                    <td><Badge tone={x.severity === "high" ? "rose" : x.severity === "medium" ? "amber" : "neutral"}>{x.severity}</Badge></td>
                  </tr>))}</tbody></table>}
          </div>
        </Card>)}</Query>
    </>
  );
}

function InsightsSection() {
  return (
    <Query<{ repo_full_name: string | null; insights: Insight[]; repositories_analysed: number }> k={["analytics-insights"]} path="/analytics/insights?days=180">{(d) => (
      <Card>
        <CardHeader title="Explainable insights" subtitle={`${d.repositories_analysed} repositories analysed · sorted by severity`} />
        <div className="grid gap-3 p-5 pt-3 md:grid-cols-2 xl:grid-cols-3">
          {d.insights.length === 0 && <EmptyState title="No insights yet" body="Insights need at least a few weeks of synced history." />}
          {d.insights.map((i) => <InsightCard key={i.id + (i.repo_full_name ?? "")} i={i} />)}
        </div>
      </Card>)}</Query>
  );
}

