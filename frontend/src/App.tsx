import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import { queryClient } from "@/lib/queryClient";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorState, Spinner } from "@/components/common/common";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { Button } from "@/components/ui/button";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const OverviewPage = lazy(() => import("@/pages/OverviewPage"));
const ReposPage = lazy(() => import("@/pages/ReposPage"));
const RepoDetailPage = lazy(() => import("@/pages/RepoDetailPage"));
const ContributorsPage = lazy(() => import("@/pages/ContributorsPage"));
const AnalyticsPage = lazy(() => import("@/pages/AnalyticsPage"));
const AssistantPage = lazy(() => import("@/pages/AssistantPage"));
const ReportsPage = lazy(() => import("@/pages/ReportsPage"));
const PipelinesPage = lazy(() => import("@/pages/PipelinesPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

function Guard({ children }: { children: ReactNode }) {
  const { me, loading, sessionError, retrySession } = useAuth();
  const location = useLocation();
  if (loading) return <div className="grid min-h-dvh place-items-center"><Spinner label="Checking session" /></div>;
  if (!me && sessionError) {
    // The key may still be valid; the API just could not confirm it. Offer a retry instead of logging out.
    return (
      <div className="grid min-h-dvh place-items-center p-6">
        <div className="max-w-md rounded-2xl border border-white/10 bg-ink-900/70 p-2">
          <ErrorState error={sessionError} onRetry={retrySession} />
          <div className="pb-4 text-center"><Button variant="ghost" size="sm" onClick={() => window.location.assign("/login")}>Back to sign-in</Button></div>
        </div>
      </div>
    );
  }
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

function Fallback() {
  return <div className="grid min-h-[40vh] place-items-center"><Spinner label="Loading view" /></div>;
}

export default function App() {
  return (
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<Fallback />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<Guard><AppShell /></Guard>}>
                <Route index element={<OverviewPage />} />
                <Route path="repos" element={<ReposPage />} />
                <Route path="repos/:owner/:name" element={<RepoDetailPage />} />
                <Route path="contributors" element={<ContributorsPage />} />
                <Route path="analytics" element={<AnalyticsPage />} />
                <Route path="assistant" element={<AssistantPage />} />
                <Route path="reports" element={<ReportsPage />} />
                <Route path="pipelines" element={<PipelinesPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  );
}
