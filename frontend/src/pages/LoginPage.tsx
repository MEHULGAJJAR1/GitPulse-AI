import { motion } from "framer-motion";
import { Activity, KeyRound, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, me, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (!loading && me) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return setError("Enter your GitPulse API key.");
    setBusy(true);
    setError(null);
    try {
      await login(key);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That key was not recognised." : "Could not reach the GitPulse API. Is the backend running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden p-6">
      <div className="pointer-events-none absolute -left-40 top-20 h-96 w-96 rounded-full bg-cyan-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-40 bottom-10 h-96 w-96 rounded-full bg-violet-500/20 blur-3xl" />
      <motion.div initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.45 }}
        className="glass-strong relative w-full max-w-md rounded-3xl p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-violet-500 shadow-lg shadow-cyan-500/30"><Activity className="h-6 w-6 text-ink-950" /></div>
          <div>
            <h1 className="text-2xl font-semibold text-white">GitPulse</h1>
            <p className="text-sm text-slate-400">GitHub activity analytics</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <label className="block text-sm font-medium text-slate-300" htmlFor="api-key">API key</label>
          <div className="relative">
            <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input id="api-key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} className="pl-9" placeholder="paste your viewer, analyst or admin key" />
          </div>
          {error && <p className="text-sm text-rose-300" role="alert">{error}</p>}
          <Button type="submit" className="w-full" size="lg" disabled={busy}>{busy ? "Verifying…" : "Sign in"}</Button>
        </form>
        <div className="mt-6 flex gap-2 rounded-xl bg-white/5 p-3 text-xs text-slate-400">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
          <span>Keys are held for this browser session only and sent as an <code className="text-slate-200">X-API-Key</code> header. Keys are created during setup (see <code className="text-slate-200">.env</code>).</span>
        </div>
      </motion.div>
    </div>
  );
}
