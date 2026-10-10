import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Plus, Power, Trash2, Radio } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Badge, Card, CardHeader, Input, Select } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { DataModeBanner, EmptyState, ErrorState, Loading, PageHeader, Stat } from "@/components/common/common";
import { api, streamEvents } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, num, timeAgo } from "@/lib/format";
import type { LogLine, PipelineStatus, QualityCheck, Run, Target } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, "emerald" | "rose" | "amber" | "cyan" | "neutral"> = {
  succeeded: "emerald", failed: "rose", partial: "amber", running: "cyan", queued: "neutral",
};

export default function PipelinesPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const status = useQuery({ queryKey: ["pipeline-status"], queryFn: ({ signal }) => api.get<PipelineStatus>("/pipeline/status", signal), refetchInterval: 5000 });
  const runs = useQuery({ queryKey: ["pipeline-runs"], queryFn: ({ signal }) => api.get<{ items: Run[] }>("/pipeline/runs?limit=20", signal), refetchInterval: 5000 });
  const targets = useQuery({ queryKey: ["pipeline-targets"], queryFn: ({ signal }) => api.get<{ items: Target[] }>("/pipeline/targets", signal) });
  const quality = useQuery({ queryKey: ["pipeline-quality"], queryFn: ({ signal }) => api.get<{ items: QualityCheck[]; summary: Record<string, number> }>("/pipeline/quality", signal) });

  useEffect(() => {
    if (selected === null && runs.data?.items.length) setSelected(runs.data.items[0].id);
  }, [runs.data, selected]);

  const s = status.data;
  return (
    <>
      <PageHeader eyebrow="Operations" title="Pipelines" description="Ingest GitHub repositories through the ELT pipeline, watch each stage live, and review data-quality checks. Viewers have read-only access."
        actions={<Badge tone={s?.github_token_configured ? "emerald" : "amber"}>{s?.github_token_configured ? "GitHub token configured" : "Anonymous GitHub quota (no token)"}</Badge>} />
      {s && <DataModeBanner mode={s.data_mode} />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="p-4"><Stat label="Current run" value={s?.running ? `#${s.running.id} · ${s.running.stage ?? s.running.status}` : "idle"} hint={s?.running ? `started ${timeAgo(s.running.started_at)}` : "no run in progress"} tone={s?.running ? "good" : "neutral"} /></Card>
        <Card className="p-4"><Stat label="Last run" value={s?.last_run ? `#${s.last_run.id} ${s.last_run.status}` : "never"} hint={s?.last_run ? timeAgo(s.last_run.finished_at ?? s.last_run.created_at) : undefined} tone={s?.last_run?.status === "failed" ? "bad" : s?.last_run?.status === "succeeded" ? "good" : "neutral"} /></Card>
        <Card className="p-4"><Stat label="Tracked targets" value={`${s?.targets.enabled ?? 0} / ${s?.targets.total ?? 0}`} hint="enabled / total" /></Card>
        <Card className="p-4"><Stat label="Scheduler" value={s ? (s.scheduler_minutes > 0 ? `every ${s.scheduler_minutes} min` : "disabled") : "–"} hint="in-app scheduler (PIPELINE_SCHEDULE_MINUTES)" /></Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="grid content-start gap-4 xl:col-span-1">
          {can("analyst") && <RunForm onStarted={(id) => { setSelected(id); qc.invalidateQueries({ queryKey: ["pipeline-runs"] }); qc.invalidateQueries({ queryKey: ["pipeline-status"] }); }} isAdmin={can("admin")} />}
          <TargetsCard targets={targets.data?.items} loading={targets.isLoading} error={targets.error} canEdit={can("analyst")} canDelete={can("admin")} onChange={() => qc.invalidateQueries({ queryKey: ["pipeline-targets"] })} />
        </div>
        <div className="grid content-start gap-4 xl:col-span-2">
          <Card>
            <CardHeader title="Run history" subtitle="Most recent 20 runs" />
            <div className="overflow-x-auto p-5 pt-3">
              {runs.isLoading ? <Loading rows={4} /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : !runs.data?.items.length ? <EmptyState title="No runs yet" body="Start a run above, or add a repository first." /> :
                <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">Run</th><th>Mode</th><th>Status</th><th className="text-right">Duration</th><th className="text-right">Started</th></tr></thead>
                  <tbody className="divide-y divide-white/5">{runs.data.items.map((r) => (
                    <tr key={r.id} onClick={() => setSelected(r.id)} className={cn("cursor-pointer hover:bg-white/[0.03]", selected === r.id && "bg-cyan-400/5")}>
                      <td className="py-2.5 font-medium text-slate-200">#{r.id} <span className="text-xs text-slate-500">{r.trigger}</span></td>
                      <td className="text-xs text-slate-400">{(r.targets?.mode ?? (r.stats as any)?.mode ?? "github")}{(r.targets?.mode ?? "github") !== "github" && <Badge className="ml-2" tone="violet">synthetic</Badge>}</td>
                      <td><Badge tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Badge>{r.error && <span className="ml-2 text-xs text-rose-300" title={r.error}>error</span>}</td>
                      <td className="text-right tabular-nums text-slate-400">{r.duration_seconds ? `${r.duration_seconds.toFixed(0)} s` : "–"}</td>
                      <td className="text-right text-xs text-slate-500">{dateLabel(r.created_at)}</td>
                    </tr>))}</tbody></table>}
            </div>
          </Card>
          {selected !== null && <RunLogs runId={selected} />}
          <Card>
            <CardHeader title="Data-quality checks" subtitle={quality.data ? `${quality.data.summary.pass ?? 0} pass · ${quality.data.summary.warn ?? 0} warn · ${quality.data.summary.fail ?? 0} fail` : ""} />
            <div className="overflow-x-auto p-5 pt-3">
              {quality.isLoading ? <Loading rows={3} /> : !quality.data?.items.length ? <EmptyState title="No quality results" body="Checks run after each transform." /> :
                <table className="w-full text-sm"><thead className="text-left text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="py-2">Model</th><th>Check</th><th>Detail</th><th>Result</th></tr></thead>
                  <tbody className="divide-y divide-white/5">{quality.data.items.slice(0, 40).map((c, i) => (
                    <tr key={`${c.run_id}-${c.check_name}-${i}`}><td className="py-2 font-mono text-xs text-slate-400">{c.model}</td><td className="text-slate-200">{c.check_name}</td>
                      <td className="max-w-[300px] truncate text-xs text-slate-500" title={c.detail ?? ""}>{c.detail}</td>
                      <td><Badge tone={c.status === "pass" ? "emerald" : c.status === "warn" ? "amber" : "rose"}>{c.status}{c.failing_rows ? ` · ${num(c.failing_rows)}` : ""}</Badge></td></tr>))}</tbody></table>}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function RunForm({ onStarted, isAdmin }: { onStarted: (id: number) => void; isAdmin: boolean }) {
  const [mode, setMode] = useState<"github" | "synthetic_seed" | "synthetic_clear">("github");
  const [targets, setTargets] = useState("");
  const [error, setError] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () => api.post<{ run_id: number; labelled_synthetic: boolean }>("/pipeline/runs", {
      mode, targets: targets.trim() ? targets.split(",").map((t) => t.trim()).filter(Boolean) : null,
    }),
    onSuccess: (res) => { setError(null); onStarted(res.run_id); },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not start the run"),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); start.mutate(); };
  return (
    <Card>
      <CardHeader title="Start a run" subtitle="Ingests enabled targets, or the listed repositories" />
      <form onSubmit={submit} className="space-y-3 p-5 pt-3 text-sm">
        <label className="block"><span className="mb-1 block text-xs text-slate-400">Mode</span>
          <Select aria-label="Run mode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className="w-full">
            <option value="github" className="bg-ink-900">Live GitHub (REST API)</option>
            {isAdmin && <option value="synthetic_seed" className="bg-ink-900">Seed DEMO synthetic data (labelled)</option>}
            {isAdmin && <option value="synthetic_clear" className="bg-ink-900">Clear DEMO synthetic data</option>}
          </Select></label>
        {mode === "github" && <label className="block"><span className="mb-1 block text-xs text-slate-400">Repositories (optional, comma-separated)</span>
          <Input aria-label="Target repositories" value={targets} onChange={(e) => setTargets(e.target.value)} placeholder="octocat/Hello-World, pallets/click" /></label>}
        {mode !== "github" && <p className="rounded-lg bg-violet-400/5 p-2 text-xs text-violet-200">Synthetic modes write rows flagged <code>data_source=synthetic</code>. They are clearly labelled throughout the app and are not GitHub data.</p>}
        {error && <p className="text-xs text-rose-300" role="alert">{error}</p>}
        <Button type="submit" className="w-full" disabled={start.isPending}><Play className="h-4 w-4" /> {start.isPending ? "Starting…" : "Start run"}</Button>
      </form>
    </Card>
  );
}

function TargetsCard({ targets, loading, error, canEdit, canDelete, onChange }: {
  targets?: Target[]; loading: boolean; error: unknown; canEdit: boolean; canDelete: boolean; onChange: () => void;
}) {
  const [kind, setKind] = useState<"repo" | "user" | "org">("repo");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => api.post("/pipeline/targets", { kind, name: name.trim() }),
    onSuccess: () => { setName(""); setErr(null); onChange(); },
    onError: (e) => setErr(e instanceof Error ? e.message : "Could not add target"),
  });
  const toggle = useMutation({ mutationFn: (t: Target) => api.patch(`/pipeline/targets/${t.id}?enabled=${!t.enabled}`), onSuccess: onChange });
  const remove = useMutation({ mutationFn: (t: Target) => api.del(`/pipeline/targets/${t.id}`), onSuccess: onChange });
  return (
    <Card>
      <CardHeader title="Tracked targets" subtitle="Repositories, users or orgs synced on each run" />
      <div className="space-y-3 p-5 pt-3 text-sm">
        {canEdit && (
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate(); }} className="flex flex-wrap gap-2">
            <Select aria-label="Target kind" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className="w-24">
              <option value="repo" className="bg-ink-900">repo</option><option value="user" className="bg-ink-900">user</option><option value="org" className="bg-ink-900">org</option>
            </Select>
            <Input aria-label="Target name" value={name} onChange={(e) => setName(e.target.value)} placeholder={kind === "repo" ? "owner/name" : "login"} className="min-w-[150px] flex-1" maxLength={140} />
            <Button type="submit" size="icon" aria-label="Add target" disabled={!name.trim() || add.isPending}><Plus className="h-4 w-4" /></Button>
            {err && <p className="w-full text-xs text-rose-300" role="alert">{err}</p>}
          </form>)}
        {loading ? <Loading rows={3} /> : error ? <ErrorState error={error} /> : !targets?.length ? <EmptyState title="No targets" body="Add a repository to begin ingesting." /> :
          <ul className="divide-y divide-white/5">{targets.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0"><p className={cn("truncate font-medium", t.enabled ? "text-slate-100" : "text-slate-500 line-through")}>{t.name}</p>
                <p className="text-[11px] text-slate-500">{t.kind} · synced {timeAgo(t.last_synced_at)}</p></div>
              <div className="flex shrink-0 gap-1">
                {canEdit && <Button variant="ghost" size="icon" aria-label={t.enabled ? "Disable target" : "Enable target"} onClick={() => toggle.mutate(t)}><Power className={cn("h-4 w-4", t.enabled ? "text-emerald-300" : "text-slate-500")} /></Button>}
                {canDelete && <Button variant="ghost" size="icon" aria-label="Delete target" onClick={() => { if (confirm(`Delete ${t.name}? Its stored data is kept.`)) remove.mutate(t); }}><Trash2 className="h-4 w-4 text-rose-300" /></Button>}
              </div>
            </li>))}</ul>}
      </div>
    </Card>
  );
}

function RunLogs({ runId }: { runId: number }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [live, setLive] = useState(false);
  const [state, setState] = useState<string>("loading");
  const endRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  useEffect(() => {
    setLines([]);
    setState("loading");
    const ctrl = new AbortController();
    setLive(true);
    (async () => {
      try {
        await streamEvents(`/pipeline/runs/${runId}/stream`, (ev) => {
          if (ev.event === "log") setLines((prev) => [...prev, ev.data as LogLine].slice(-500));
          else if (ev.event === "status") setState((ev.data as { status?: string }).status ?? "running");
          else if (ev.event === "end") { setState((ev.data as { status?: string }).status ?? "finished"); }
        }, ctrl.signal);
      } catch {
        if (!ctrl.signal.aborted) {
          const res = await api.get<{ items: LogLine[] }>(`/pipeline/runs/${runId}/logs?limit=500`).catch(() => ({ items: [] as LogLine[] }));
          setLines(res.items);
        }
      } finally {
        setLive(false);
        qc.invalidateQueries({ queryKey: ["pipeline-runs"] });
        qc.invalidateQueries({ queryKey: ["pipeline-quality"] });
      }
    })();
    return () => ctrl.abort();
  }, [runId, qc]);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [lines.length]);

  return (
    <Card>
      <CardHeader title={`Run #${runId} logs`} subtitle={live ? "Streaming over SSE…" : `Stream closed · ${state}`} action={live ? <Badge tone="cyan"><Radio className="mr-1 h-3 w-3 animate-pulse" /> live</Badge> : <Badge>{state}</Badge>} />
      <div className="max-h-80 overflow-y-auto p-4 pt-3 font-mono text-[12px] leading-relaxed scrollbar-thin" role="log" aria-live="off">
        {lines.length === 0 ? <p className="text-slate-500">{live ? "Waiting for log lines…" : "No log lines for this run."}</p> : lines.map((l) => (
          <div key={l.id} className="flex gap-2">
            <span className="shrink-0 text-slate-600">{l.ts?.slice(11, 19)}</span>
            <span className={cn("shrink-0 w-14", l.level === "ERROR" ? "text-rose-300" : l.level === "WARNING" ? "text-amber-300" : "text-cyan-300/80")}>{l.level}</span>
            {l.stage && <span className="shrink-0 text-violet-300/80">[{l.stage}]</span>}
            <span className="break-all text-slate-300">{l.message}</span>
          </div>))}
        <div ref={endRef} />
      </div>
    </Card>
  );
}
