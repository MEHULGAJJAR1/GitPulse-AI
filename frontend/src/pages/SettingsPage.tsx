import { useQuery } from "@tanstack/react-query";
import { LogOut, ShieldCheck, ServerCog } from "lucide-react";
import { Badge, Card, CardHeader } from "@/components/ui/primitives";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading, PageHeader, Stat } from "@/components/common/common";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AiStatus, MeResponse } from "@/lib/types";

interface Health { status: string; version: string; database: string; github_token_configured: boolean; llm: { provider: string; model: string | null; enabled: boolean; base_url_host: string }; auth_configured: boolean; scheduler_minutes: number }

export default function SettingsPage() {
  const { me, logout, can } = useAuth();
  const health = useQuery({ queryKey: ["health"], queryFn: ({ signal }) => api.get<Health>("/health", signal), refetchInterval: 30_000 });
  const ai = useQuery({ queryKey: ["ai-status"], queryFn: ({ signal }) => api.get<AiStatus>("/ai/status", signal), staleTime: 60_000 });
  const config = useQuery({ queryKey: ["admin-config"], queryFn: ({ signal }) => api.get<Record<string, unknown>>("/admin/config", signal), enabled: can("admin"), retry: false });
  const profile = me as MeResponse | null;

  return (
    <>
      <PageHeader eyebrow="Account" title="Settings" description="Your access level, service health and configuration. Secrets are never displayed; the server redacts them." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Your access" subtitle="Role is resolved from your API key on the server" action={<Button variant="outline" size="sm" onClick={logout}><LogOut className="h-4 w-4" /> Sign out</Button>} />
          <div className="grid grid-cols-2 gap-4 p-5 pt-3 text-sm">
            <Stat label="Role" value={profile?.role ?? "–"} />
            <Stat label="Private repos" value={profile?.can_see_private_repos ? "visible" : "hidden"} hint={profile?.private_repos_enabled ? "feature enabled" : "feature disabled on server"} />
            <div className="col-span-2 rounded-xl bg-white/[0.03] p-3 text-xs text-slate-400">
              <p className="mb-1 font-medium text-slate-300">Role capabilities</p>
              <ul className="list-disc space-y-0.5 pl-4">
                <li><b>viewer</b> — read dashboards, analytics, exports and the assistant.</li>
                <li><b>analyst</b> — also manage tracked targets and start GitHub ingestion runs.</li>
                <li><b>admin</b> — also seed/clear labelled synthetic demo data, delete targets, view redacted configuration.</li>
              </ul>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Service health" subtitle="Polled every 30 seconds" action={health.data && <Badge tone={health.data.status === "ok" ? "emerald" : "rose"}>{health.data.status}</Badge>} />
          <div className="p-5 pt-3">
            {health.isLoading ? <Loading rows={3} /> : health.error ? <ErrorState error={health.error} onRetry={() => health.refetch()} /> : health.data && (
              <div className="grid grid-cols-2 gap-4 text-sm">
                <Stat label="Database" value={health.data.database} tone={health.data.database === "up" ? "good" : "bad"} />
                <Stat label="API version" value={health.data.version} />
                <Stat label="GitHub token" value={health.data.github_token_configured ? "configured" : "not set"} hint={health.data.github_token_configured ? undefined : "anonymous rate limit applies"} />
                <Stat label="Scheduler" value={health.data.scheduler_minutes > 0 ? `${health.data.scheduler_minutes} min` : "disabled"} />
              </div>)}
          </div>
        </Card>
        <Card>
          <CardHeader title="AI assistant" subtitle="Grounded answers; LLM narration is optional" action={<ShieldCheck className="h-4 w-4 text-emerald-300" />} />
          <div className="grid grid-cols-2 gap-4 p-5 pt-3 text-sm">
            <Stat label="Provider" value={ai.data?.provider ?? "–"} hint={ai.data?.base_url_host} />
            <Stat label="Model" value={ai.data?.model ?? "–"} />
            <p className="col-span-2 text-xs text-slate-500">{ai.data?.note ?? "Rule-based fallback is always available."}</p>
          </div>
        </Card>
        {can("admin") && (
          <Card>
            <CardHeader title="Configuration (redacted)" subtitle="Values come from the server environment; secrets show as ••••" action={<ServerCog className="h-4 w-4 text-slate-400" />} />
            <div className="p-5 pt-3">
              {config.isLoading ? <Loading rows={4} /> : config.error ? <ErrorState error={config.error} /> :
                <dl className="grid max-h-80 grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-x-4 gap-y-1 overflow-y-auto text-xs scrollbar-thin">
                  {Object.entries(config.data ?? {}).map(([k, v]) => (
                    <div key={k} className="contents"><dt className="truncate font-mono text-slate-400">{k}</dt><dd className="truncate font-mono text-slate-200">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>))}
                </dl>}
            </div>
          </Card>)}
      </div>
    </>
  );
}
