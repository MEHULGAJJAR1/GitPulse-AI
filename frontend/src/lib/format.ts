export function num(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function pct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return "–";
  return `${n.toFixed(digits)}%`;
}

export function signedPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

export function hours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "–";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(h < 10 ? 1 : 0)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

export function dateLabel(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: iso && iso.length > 10 ? "numeric" : undefined });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "–";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function gradeColor(grade: string): string {
  return (
    { A: "text-emerald-300 bg-emerald-400/10 border-emerald-400/30", B: "text-cyan-300 bg-cyan-400/10 border-cyan-400/30",
      C: "text-amber-300 bg-amber-400/10 border-amber-400/30", D: "text-orange-300 bg-orange-400/10 border-orange-400/30",
      E: "text-rose-300 bg-rose-400/10 border-rose-400/30" } as Record<string, string>
  )[grade] ?? "text-slate-300 bg-slate-400/10 border-slate-400/30";
}

export function severityColor(sev: string): string {
  return (
    { high: "text-rose-300 bg-rose-400/10 border-rose-400/30", medium: "text-amber-300 bg-amber-400/10 border-amber-400/30",
      low: "text-sky-300 bg-sky-400/10 border-sky-400/30", info: "text-violet-300 bg-violet-400/10 border-violet-400/30" } as Record<string, string>
  )[sev] ?? "text-slate-300 bg-slate-400/10 border-slate-400/30";
}
