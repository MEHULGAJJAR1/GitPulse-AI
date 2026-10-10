import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  delta?: number | null;
  accent?: "cyan" | "violet" | "emerald" | "amber" | "rose";
  index?: number;
}

const ACCENTS = {
  cyan: "from-cyan-400/25 to-cyan-400/0 text-cyan-300",
  violet: "from-violet-400/25 to-violet-400/0 text-violet-300",
  emerald: "from-emerald-400/25 to-emerald-400/0 text-emerald-300",
  amber: "from-amber-400/25 to-amber-400/0 text-amber-300",
  rose: "from-rose-400/25 to-rose-400/0 text-rose-300",
};

export function KpiCard({ label, value, hint, icon: Icon, delta, accent = "cyan", index = 0 }: Props) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04, duration: 0.35 }}>
      <Card className="group relative overflow-hidden p-4 transition hover:-translate-y-0.5 hover:border-white/20">
        <div className={cn("pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-gradient-to-br blur-xl", ACCENTS[accent].split(" ")[0], ACCENTS[accent].split(" ")[1])} />
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-400">{label}</span>
          <span className={cn("rounded-lg border border-white/10 bg-white/5 p-1.5", ACCENTS[accent].split(" ")[2])}><Icon className="h-4 w-4" /></span>
        </div>
        <div className="mt-3 text-2xl font-semibold tabular-nums tracking-tight text-white">{value}</div>
        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
          {delta !== undefined && delta !== null && (
            <span className={cn("font-medium", delta >= 0 ? "text-emerald-300" : "text-rose-300")}>
              {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
            </span>
          )}
          {hint && <span className="truncate">{hint}</span>}
        </div>
      </Card>
    </motion.div>
  );
}
