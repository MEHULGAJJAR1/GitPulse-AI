import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, Pie, PieChart, Cell,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChartBox } from "@/components/common/common";
import { num } from "@/lib/format";
import type { Forecast, LanguageRow, TimelinePoint } from "@/lib/types";

const PALETTE = ["#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa", "#fb7185", "#2dd4bf", "#c084fc", "#facc15"];
export const tooltipStyle = {
  contentStyle: { background: "rgba(10,14,24,0.95)", border: "1px solid rgba(148,163,184,0.2)", borderRadius: 12, fontSize: 12 },
  labelStyle: { color: "#cbd5e1" },
  itemStyle: { color: "#e2e8f0" },
};
const axis = { stroke: "#334155", tick: { fill: "#94a3b8", fontSize: 11 } };

export function ActivityTimeline({ data, height = 280 }: { data: TimelinePoint[]; height?: number }) {
  return (
    <ChartBox height={height}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="gCommits" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} /><stop offset="100%" stopColor="#22d3ee" stopOpacity={0} /></linearGradient>
            <linearGradient id="gPrs" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity={0.35} /><stop offset="100%" stopColor="#a78bfa" stopOpacity={0} /></linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey="date" {...axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip {...tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          <Area type="monotone" dataKey="commits" name="Commits" stroke="#22d3ee" fill="url(#gCommits)" strokeWidth={2} />
          <Area type="monotone" dataKey="prs_merged" name="PRs merged" stroke="#a78bfa" fill="url(#gPrs)" strokeWidth={2} />
          <Line type="monotone" dataKey="issues_closed" name="Issues closed" stroke="#34d399" dot={false} strokeWidth={1.5} />
        </AreaChart>
      </ResponsiveContainer>
    </ChartBox>
  );
}

export function LanguageDonut({ items }: { items: LanguageRow[] }) {
  const top = items.slice(0, 7);
  return (
    <div className="grid items-center gap-4 sm:grid-cols-2">
      <ChartBox height={200}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={top} dataKey="bytes_total" nameKey="language" innerRadius={55} outerRadius={85} paddingAngle={3} stroke="none">
              {top.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip {...tooltipStyle} formatter={(v) => `${num(Number(v))} bytes`} />
          </PieChart>
        </ResponsiveContainer>
      </ChartBox>
      <ul className="space-y-2 text-sm">
        {top.map((l, i) => (
          <li key={l.language} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-slate-300"><span className="h-2.5 w-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />{l.language}</span>
            <span className="tabular-nums text-slate-400">{(l.share * 100).toFixed(1)}% <span className="text-slate-600">· {l.repos} repo(s)</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Forecast chart: observed history (solid) + predictions (dashed) with 80% and 95% bands. */
export function ForecastChart({ forecast }: { forecast: Forecast }) {
  if (forecast.status !== "ok" || !forecast.history || !forecast.forecast) return null;
  const rows = [
    ...forecast.history.map((h) => ({ date: h.date, actual: h.value, predicted: null as number | null, band95: null as [number, number] | null, band80: null as [number, number] | null })),
    ...forecast.forecast.map((f) => ({ date: f.date, actual: null, predicted: f.predicted, band95: [f.lower_95, f.upper_95] as [number, number], band80: [f.lower_80, f.upper_80] as [number, number] })),
  ];
  // Stacked-area trick for range bands: transparent base + band height.
  const data = rows.map((r) => ({
    ...r,
    base95: r.band95?.[0] ?? null, h95: r.band95 ? r.band95[1] - r.band95[0] : null,
    base80: r.band80?.[0] ?? null, h80: r.band80 ? r.band80[1] - r.band80[0] : null,
  }));
  const boundary = forecast.history[forecast.history.length - 1]?.date;
  return (
    <ChartBox height={300}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey="date" {...axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={22} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip {...tooltipStyle} />
          <Area type="monotone" dataKey="base95" stackId="95" stroke="none" fill="transparent" legendType="none" isAnimationActive={false} />
          <Area type="monotone" dataKey="h95" stackId="95" name="95% interval" stroke="none" fill="#a78bfa" fillOpacity={0.12} />
          <Area type="monotone" dataKey="base80" stackId="80" stroke="none" fill="transparent" legendType="none" isAnimationActive={false} />
          <Area type="monotone" dataKey="h80" stackId="80" name="80% interval" stroke="none" fill="#22d3ee" fillOpacity={0.22} />
          <Line type="monotone" dataKey="actual" name="Observed" stroke="#e2e8f0" strokeWidth={2} dot={false} connectNulls={false} />
          <Line type="monotone" dataKey="predicted" name="Predicted" stroke="#22d3ee" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 2 }} connectNulls={false} />
          {boundary && <ReferenceLine x={boundary} stroke="#475569" strokeDasharray="3 3" label={{ value: "today", fill: "#64748b", fontSize: 10, position: "insideTopRight" }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartBox>
  );
}

export function WeekdayBars({ profile }: { profile: { day: string; mean: number; index: number }[] }) {
  return (
    <ChartBox height={200}>
      <ResponsiveContainer>
        <BarChart data={profile} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey="day" {...axis} />
          <YAxis {...axis} />
          <Tooltip {...tooltipStyle} formatter={(v) => Number(v).toFixed(2)} />
          <Bar dataKey="mean" name="Mean per day" radius={[6, 6, 0, 0]} fill="#a78bfa" />
        </BarChart>
      </ResponsiveContainer>
    </ChartBox>
  );
}

export function Histogram({ data, color = "#22d3ee", height = 220, xKey = "bucket", yKey = "count", yName = "Count" }:
  { data: Record<string, string | number>[]; color?: string; height?: number; xKey?: string; yKey?: string; yName?: string }) {
  return (
    <ChartBox height={height}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey={xKey} {...axis} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip {...tooltipStyle} />
          <Bar dataKey={yKey} name={yName} fill={color} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartBox>
  );
}

export function MultiLine({ data, xKey, lines, height = 260 }: {
  data: Record<string, string | number | null>[]; xKey: string; lines: { key: string; name: string; color: string }[]; height?: number;
}) {
  return (
    <ChartBox height={height}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey={xKey} {...axis} tickFormatter={(d: string) => String(d).slice(5)} minTickGap={24} />
          <YAxis {...axis} />
          <Tooltip {...tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          {lines.map((l) => <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={2} dot={false} connectNulls />)}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartBox>
  );
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Developer contribution heatmap: weekday (rows) x UTC hour (columns). */
export function WeekdayHourHeatmap({ data }: { data: { weekday: number; hour_utc: number; commits: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.commits));
  const cell = (w: number, h: number) => data.find((d) => d.weekday === w && d.hour_utc === h)?.commits ?? 0;
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <div className="min-w-[560px]">
        <div className="grid grid-cols-[40px_repeat(24,minmax(0,1fr))] gap-1 text-[10px] text-slate-500">
          <span />
          {Array.from({ length: 24 }).map((_, h) => <span key={h} className="text-center">{h % 3 === 0 ? h : ""}</span>)}
        </div>
        {DAYS.map((day, i) => (
          <div key={day} className="mt-1 grid grid-cols-[40px_repeat(24,minmax(0,1fr))] gap-1">
            <span className="self-center text-[11px] text-slate-500">{day}</span>
            {Array.from({ length: 24 }).map((_, h) => {
              const v = cell(i + 1, h);
              const alpha = v === 0 ? 0.04 : 0.15 + 0.85 * (v / max);
              return (
                <span key={h} title={`${day} ${h}:00 UTC · ${v} commit(s)`} className="aspect-square rounded-[4px] transition hover:ring-1 hover:ring-white/40"
                  style={{ background: `rgba(34,211,238,${alpha.toFixed(3)})` }} />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/** GitHub-style calendar: one column per week, one row per weekday (Mon..Sun). */
export function CalendarHeatmap({ data, days }: { data: { date: string; commits: number }[]; days: number }) {
  const map = new Map(data.map((d) => [d.date, d.commits]));
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - (days - 1));
  const offset = (start.getDay() + 6) % 7; // Monday-based
  const cells: { date: string; commits: number }[] = [];
  for (let i = 0; i < offset; i++) cells.push({ date: "", commits: -1 });
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = d.toISOString().slice(0, 10);
    cells.push({ date: key, commits: map.get(key) ?? 0 });
  }
  const weeks: typeof cells[] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  const max = Math.max(1, ...data.map((d) => d.commits));
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <div className="flex gap-[3px]">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {week.map((c, di) => (
              <span key={di} title={c.date ? `${c.date}: ${c.commits} commit(s)` : ""}
                className="h-3 w-3 rounded-[3px]"
                style={{ background: c.commits < 0 ? "transparent" : c.commits === 0 ? "rgba(148,163,184,0.08)" : `rgba(167,139,250,${(0.2 + 0.8 * (c.commits / max)).toFixed(3)})` }} />
            ))}
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
        Less <span className="h-2.5 w-2.5 rounded-[2px] bg-slate-500/10" /><span className="h-2.5 w-2.5 rounded-[2px] bg-violet-400/40" /><span className="h-2.5 w-2.5 rounded-[2px] bg-violet-400/80" /> More
      </div>
    </div>
  );
}

export function CorrelationTable({ pairs }: { pairs: { metric_a: string; metric_b: string; spearman_rho: number; pearson_r: number; strength: string; significant: boolean }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500">
          <tr><th className="py-2 pr-3">Metric pair</th><th className="py-2 pr-3 text-right">Spearman ρ</th><th className="py-2 pr-3 text-right">Pearson r</th><th className="py-2">Strength</th></tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {pairs.map((p) => {
            const v = p.spearman_rho;
            const bg = v > 0 ? `rgba(52,211,153,${Math.min(0.5, Math.abs(v) * 0.6).toFixed(2)})` : `rgba(251,113,133,${Math.min(0.5, Math.abs(v) * 0.6).toFixed(2)})`;
            return (
              <tr key={`${p.metric_a}-${p.metric_b}`}>
                <td className="py-2 pr-3 text-slate-300">{p.metric_a.replace("_", " ")} ↔ {p.metric_b.replace("_", " ")}</td>
                <td className="py-2 pr-3 text-right"><span className="rounded-md px-2 py-0.5 font-mono tabular-nums" style={{ background: bg }}>{v.toFixed(2)}</span></td>
                <td className="py-2 pr-3 text-right tabular-nums text-slate-400">{p.pearson_r.toFixed(2)}</td>
                <td className="py-2 text-slate-400">{p.strength}{p.significant ? " · significant" : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
