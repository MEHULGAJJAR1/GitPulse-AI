import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type HTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rounded-2xl", className)} {...props} />;
}

export function CardHeader({ title, subtitle, action, className }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-5", className)}>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold tracking-tight text-slate-100">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const badge = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap", {
  variants: {
    tone: {
      neutral: "border-slate-500/30 bg-slate-500/10 text-slate-300",
      cyan: "border-cyan-400/30 bg-cyan-400/10 text-cyan-200",
      violet: "border-violet-400/30 bg-violet-400/10 text-violet-200",
      emerald: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
      amber: "border-amber-400/30 bg-amber-400/10 text-amber-200",
      rose: "border-rose-400/30 bg-rose-400/10 text-rose-200",
      sky: "border-sky-400/30 bg-sky-400/10 text-sky-200",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-10 w-full rounded-xl border border-slate-600/50 bg-ink-900/70 px-3 text-sm text-slate-100 placeholder:text-slate-500 transition focus:border-cyan-400/60 focus:outline-none focus:ring-2 focus:ring-cyan-400/20",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 rounded-xl border border-slate-600/50 bg-ink-900/70 px-3 pr-8 text-sm text-slate-100 focus:border-cyan-400/60 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 cursor-pointer",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-white/5", className)} />;
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string; icon?: ReactNode }[] }) {
  return (
    <div role="tablist" className="scrollbar-thin flex gap-1 overflow-x-auto rounded-xl border border-white/10 bg-ink-900/60 p-1">
      {items.map((it) => (
        <button
          key={it.id}
          role="tab"
          aria-selected={value === it.id}
          onClick={() => onChange(it.id)}
          className={cn(
            "flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
            value === it.id ? "bg-white/10 text-white shadow-inner" : "text-slate-400 hover:text-slate-200",
          )}
        >
          {it.icon}
          {it.label}
        </button>
      ))}
    </div>
  );
}
