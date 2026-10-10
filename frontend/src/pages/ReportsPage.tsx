import { useQuery } from "@tanstack/react-query";
import { Download, FileJson, FileSpreadsheet, Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, Card, CardHeader } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Loading, PageHeader } from "@/components/common/common";
import { InsightCard } from "./RepoDetailPage";
import { api, downloadExport } from "@/lib/api";
import { useGlobalFilters } from "@/lib/filters";
import type { Insight } from "@/lib/types";

const DATASETS: { id: string; label: string; desc: string; repo?: boolean }[] = [
  { id: "repos", label: "Repositories", desc: "One row per repository: stars, commits, PRs, health inputs, data source." },
  { id: "daily", label: "Daily metrics", desc: "Per repository and day: commits, issues, PRs, stars. Zero-filled.", repo: true },
  { id: "commits", label: "Commits", desc: "Commit metadata (SHA, author, time, headline).", repo: true },
  { id: "issues", label: "Issues", desc: "Issues with state, age and close time.", repo: true },
  { id: "pulls", label: "Pull requests", desc: "PRs with merge time and branch refs.", repo: true },
  { id: "contributors", label: "Contributors", desc: "Commit counts and activity per login.", repo: true },
  { id: "health", label: "Health scores", desc: "Health score, grade, confidence and data gaps per repo." },
  { id: "anomalies", label: "Anomalies", desc: "Flagged days with z-scores and explanations." },
];

export default function ReportsPage() {
  const { filters } = useGlobalFilters();
  const [dataset, setDataset] = useState("repos");
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [repo, setRepo] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ds = DATASETS.find((d) => d.id === dataset)!;
  const days = Math.min(Math.max(filters.days, 1), 730);

  const insights = useQuery({ queryKey: ["report-insights"], queryFn: ({ signal }) => api.get<{ insights: Insight[]; narrative?: string | null; mode?: string }>("/ai/insights", signal), staleTime: 60_000 });

  const download = async () => {
    setBusy("download"); setErr(null);
    const p = new URLSearchParams({ format, days: String(days) });
    if (ds.repo && repo) p.set("repo", repo);
    try { await downloadExport(`/exports/${dataset}?${p}`, `gitpulse-${dataset}.${format}`); }
    catch (e) { setErr(e instanceof Error ? e.message : "Export failed"); }
    finally { setBusy(null); }
  };

  return (
    <>
      <PageHeader eyebrow="Reports" title="Reports & exports" description="Export grounded datasets as CSV or JSON. Every export carries metadata with its data mode, so synthetic rows can never be mistaken for GitHub activity." />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Export center" subtitle={`Window: last ${days} days (from the page filters)`} />
          <div className="grid gap-3 p-5 pt-3 md:grid-cols-2">
            {DATASETS.map((d) => (
              <button key={d.id} onClick={() => setDataset(d.id)} aria-pressed={dataset === d.id}
                className={`rounded-xl border p-4 text-left transition ${dataset === d.id ? "border-cyan-400/50 bg-cyan-400/5" : "border-white/10 bg-white/[0.03] hover:border-white/20"}`}>
                <div className="flex items-center justify-between"><span className="font-medium text-slate-100">{d.label}</span>{d.repo && <Badge>per repo</Badge>}</div>
                <p className="mt-1 text-xs text-slate-400">{d.desc}</p>
              </button>))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Configure download" subtitle={ds.label} />
          <div className="space-y-4 p-5 pt-3 text-sm">
            <label className="block"><span className="mb-1 block text-xs text-slate-400">Format</span>
              <div className="flex gap-2">
                <Button variant={format === "csv" ? "default" : "outline"} size="sm" onClick={() => setFormat("csv")}><FileSpreadsheet className="h-4 w-4" /> CSV</Button>
                <Button variant={format === "json" ? "default" : "outline"} size="sm" onClick={() => setFormat("json")}><FileJson className="h-4 w-4" /> JSON</Button>
              </div></label>
            {ds.repo && (
              <label className="block"><span className="mb-1 block text-xs text-slate-400">Repository (optional)</span>
                <input value={repo} onChange={(e) => setRepo(e.target.value.trim())} placeholder="owner/name — blank for all" aria-label="Repository for export"
                  className="h-10 w-full rounded-xl border border-slate-600/50 bg-ink-900/70 px-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none" /></label>)}
            <Button className="w-full" onClick={download} disabled={busy !== null}><Download className="h-4 w-4" /> {busy ? "Preparing…" : `Download ${format.toUpperCase()}`}</Button>
            {err && <p className="text-xs text-rose-300" role="alert">{err}</p>}
            <p className="text-xs text-slate-500">Exports respect your role: private repositories are included only for roles permitted to see them.</p>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Narrative summary" subtitle={insights.data?.mode === "llm" ? "Narrated by the configured LLM from grounded findings" : "Rule-based summary of current findings"} action={<Sparkles className="h-4 w-4 text-cyan-300" />} />
        <div className="p-5 pt-3">
          {insights.isLoading ? <Loading rows={3} /> : insights.error ? <ErrorState error={insights.error} onRetry={() => insights.refetch()} /> :
            !insights.data?.insights.length ? <EmptyState title="No findings to report" body="Sync more history or add repositories, then return here." /> :
            <div className="grid gap-3 md:grid-cols-2">
              {insights.data.narrative && <p className="whitespace-pre-wrap rounded-xl bg-white/[0.03] p-4 text-sm leading-relaxed text-slate-200 md:col-span-2">{insights.data.narrative}</p>}
              {insights.data.insights.slice(0, 8).map((i) => <InsightCard key={i.id + (i.repo_full_name ?? "")} i={i} />)}
            </div>}
        </div>
      </Card>
    </>
  );
}
