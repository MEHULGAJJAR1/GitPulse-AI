import { motion } from "framer-motion";
import { AlertTriangle, Database, FlaskConical, Inbox, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DataMode } from "@/lib/types";

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
      className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-300/80">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">{title}</h1>
        {description && <div className="mt-1 max-w-3xl text-sm text-slate-400">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </motion.div>
  );
}

export function Section({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("grid gap-4", className)}>{children}</section>;
}

export function DataModeBanner({ mode }: { mode?: DataMode }) {
  if (!mode) return null;
  if (mode.mode === "live")
    return (
      <Banner tone="emerald" icon={<Database className="h-4 w-4" />}>
        <strong>Live GitHub data.</strong> {mode.github_repos} repositor{mode.github_repos === 1 ? "y" : "ies"} ingested from the GitHub REST API.
      </Banner>
    );
  if (mode.mode === "empty")
    return (
      <Banner tone="amber" icon={<Inbox className="h-4 w-4" />}>
        <strong>No data yet.</strong> Run the ELT pipeline from the Pipelines page to ingest GitHub activity.
      </Banner>
    );
  return (
    <Banner tone="violet" icon={<FlaskConical className="h-4 w-4" />}>
      <strong>{mode.mode === "mixed" ? "Mixed data." : "Synthetic demo data."}</strong>{" "}
      {mode.synthetic_repos} repositor{mode.synthetic_repos === 1 ? "y" : "ies"} are <Badge tone="violet">DEMO · synthetic</Badge>, deterministic fallback data,
      not GitHub activity.{mode.github_repos > 0 && ` ${mode.github_repos} repo(s) are live GitHub data.`}
    </Banner>
  );
}

function Banner({ tone, icon, children }: { tone: "emerald" | "violet" | "amber"; icon: ReactNode; children: ReactNode }) {
  const styles = {
    emerald: "border-emerald-400/25 bg-emerald-400/5 text-emerald-100",
    violet: "border-violet-400/30 bg-violet-400/5 text-violet-100",
    amber: "border-amber-400/30 bg-amber-400/5 text-amber-100",
  }[tone];
  return <div className={cn("flex items-start gap-3 rounded-xl border px-4 py-3 text-sm", styles)} role="status">
    <span className="mt-0.5">{icon}</span><div>{children}</div></div>;
}

export function DataSourceBadge({ source }: { source?: string }) {
  if (source === "synthetic") return <Badge tone="violet" title="Deterministic synthetic demo data">DEMO</Badge>;
  if (source === "github") return <Badge tone="emerald">GitHub</Badge>;
  return null;
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <Inbox className="h-8 w-8 text-slate-500" />
      <p className="font-medium text-slate-200">{title}</p>
      {body && <p className="max-w-md text-sm text-slate-400">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError ? (typeof error.detail === "string" ? error.detail : error.message) : "Something went wrong.";
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-10 text-center" role="alert">
      <AlertTriangle className="h-8 w-8 text-rose-300" />
      <p className="text-slate-200">{message}</p>
      {onRetry && <Button variant="secondary" size="sm" onClick={onRetry}><RefreshCw className="h-3.5 w-3.5" />Retry</Button>}
    </div>
  );
}

export function Loading({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("grid gap-3 p-5", className)} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-10" />)}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" />{label}</div>;
}

export function ChartBox({ children, height = 260 }: { children: ReactNode; height?: number }) {
  return <div style={{ height, width: "100%" }} className="min-w-0">{children}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "good" | "bad" | "neutral" }) {
  return (
    <div className="grid gap-0.5">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={cn("text-lg font-semibold tabular-nums", tone === "good" && "text-emerald-300", tone === "bad" && "text-rose-300")}>{value}</span>
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <Card className={cn("p-5", className)}>{children}</Card>;
}
