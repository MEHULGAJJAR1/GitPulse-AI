import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bot, Send, Sparkles, User } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Badge, Card } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader, Spinner } from "@/components/common/common";
import { api } from "@/lib/api";
import { useGlobalFilters } from "@/lib/filters";
import type { AiStatus, AskResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Turn { id: number; role: "user" | "assistant"; text: string; meta?: AskResponse; error?: string }

const SUGGESTIONS = [
  "Which repo has the most commits?",
  "Which repositories have the lowest health?",
  "Are there any anomalies in the last 30 days?",
  "What is the median PR merge time?",
  "Who are the top contributors?",
  "How many open issues are older than 90 days?",
];

export default function AssistantPage() {
  const { filters } = useGlobalFilters();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const nextId = useRef(1);
  const status = useQuery({ queryKey: ["ai-status"], queryFn: ({ signal }) => api.get<AiStatus>("/ai/status", signal), staleTime: 60_000 });

  const ask = useMutation({
    mutationFn: (question: string) => api.post<AskResponse>("/ai/ask", { question, days: Math.min(Math.max(filters.days, 7), 365) }),
    onSuccess: (res) => setTurns((t) => [...t, { id: nextId.current++, role: "assistant", text: res.answer, meta: res }]),
    onError: (err) => setTurns((t) => [...t, { id: nextId.current++, role: "assistant", text: "", error: err instanceof Error ? err.message : "Request failed" }]),
  });

  const submit = (e?: FormEvent, preset?: string) => {
    e?.preventDefault();
    const q = (preset ?? input).trim();
    if (q.length < 3 || ask.isPending) return;
    setTurns((t) => [...t, { id: nextId.current++, role: "user", text: q }]);
    setInput("");
    ask.mutate(q);
  };

  return (
    <>
      <PageHeader eyebrow="AI" title="Analytics assistant"
        description="Answers are computed from GitPulse's analytics tables first. An LLM, if configured, only narrates those results and cites the tables it used."
        actions={status.data && (
          <Badge tone={status.data.enabled ? "emerald" : "neutral"}>
            {status.data.enabled ? `LLM · ${status.data.model}` : "Rule-based (no LLM configured)"}
          </Badge>)} />

      <div className="grid gap-4 xl:grid-cols-4">
        <Card className="flex min-h-[560px] flex-col xl:col-span-3">
          <div className="flex-1 space-y-4 overflow-y-auto p-5 scrollbar-thin" aria-live="polite">
            {turns.length === 0 && (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400/30 to-violet-500/30"><Sparkles className="h-6 w-6 text-cyan-200" /></div>
                  <p className="text-sm text-slate-300">Ask about repositories, contributors, delivery speed or anomalies.</p>
                  <p className="mt-1 text-xs text-slate-500">Window: last {Math.min(Math.max(filters.days, 7), 365)} days (set on the page filters).</p>
                </div>
              </div>)}
            {turns.map((t) => (
              <motion.div key={t.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={cn("flex gap-3", t.role === "user" && "justify-end")}>
                {t.role === "assistant" && <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-cyan-400/15"><Bot className="h-4 w-4 text-cyan-200" /></div>}
                <div className={cn("max-w-[85%] rounded-2xl px-4 py-3 text-sm", t.role === "user" ? "bg-violet-500/20 text-violet-50" : "border border-white/10 bg-white/[0.03] text-slate-200")}>
                  {t.error ? <p className="text-rose-300">{t.error}</p> : <p className="whitespace-pre-wrap leading-relaxed">{t.text}</p>}
                  {t.meta && (
                    <div className="mt-3 space-y-2 border-t border-white/10 pt-2 text-xs text-slate-400">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={t.meta.mode === "llm" ? "violet" : "cyan"}>{t.meta.mode === "llm" ? "LLM-narrated" : "Rule-based"}</Badge>
                        <Badge>intent: {t.meta.intent}</Badge>
                        {t.meta.grounded_in.map((g) => <Badge key={g} className="font-mono">{g}</Badge>)}
                      </div>
                      <p className="text-slate-500">{t.meta.note}</p>
                    </div>)}
                </div>
                {t.role === "user" && <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-violet-500/20"><User className="h-4 w-4 text-violet-200" /></div>}
              </motion.div>))}
            {ask.isPending && <Spinner label="Querying analytics tables" />}
          </div>
          <form onSubmit={(e) => submit(e)} className="flex gap-2 border-t border-white/10 p-4">
            <input aria-label="Question" value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} placeholder="Ask GitPulse a question…"
              className="h-11 flex-1 rounded-xl border border-slate-600/50 bg-ink-900/70 px-4 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none focus:ring-2 focus:ring-cyan-400/20" />
            <Button type="submit" disabled={input.trim().length < 3 || ask.isPending}><Send className="h-4 w-4" /> Ask</Button>
          </form>
        </Card>

        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Suggested questions</p>
          <div className="flex flex-col gap-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => submit(undefined, s)} disabled={ask.isPending}
                className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-left text-sm text-slate-300 transition hover:border-cyan-400/40 hover:bg-cyan-400/5 disabled:opacity-50">{s}</button>))}
          </div>
          <div className="mt-5 rounded-xl bg-white/[0.03] p-3 text-xs text-slate-500">
            {status.error ? <ErrorState error={status.error} /> : status.data?.note}
          </div>
        </Card>
      </div>
    </>
  );
}
