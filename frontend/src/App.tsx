import { Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AppLayout } from "@/layout/AppLayout";
import { LoginPage } from "@/pages/LoginPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { RequestsPage } from "@/pages/RequestsPage";
import { ProvidersPage } from "@/pages/ProvidersPage";
import { CostsPage } from "@/pages/CostsPage";
import { CachePage } from "@/pages/CachePage";
import { RateLimitsPage } from "@/pages/RateLimitsPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { LiveActivityPage } from "@/pages/LiveActivityPage";
import { SystemHealthPage } from "@/pages/SystemHealthPage";
import { useAuthMe } from "@/api/queries";

export default function App() {
  const me = useAuthMe();

  // Authenticated — a confirmed session. Show the dashboard.
  if (me.data) return <AppRoutes />;

  // The session check failed (a 401, or any error with no cached user) — sign in.
  if (me.isError) return <LoginPage />;

  // Still resolving the session.
  return (
    <div className="flex h-full min-h-screen w-full flex-col items-center justify-center bg-bg text-text animate-in">
      <div className="relative flex flex-col items-center gap-4">
        <div className="relative grid size-11 place-items-center rounded-xl bg-accent text-accent-fg shadow-lg shadow-accent/20">
          <Loader2 className="size-5 animate-spin" />
        </div>
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-sm font-semibold tracking-tight text-text">InferMesh</span>
          <span className="text-xs text-text-muted">Connecting to gateway console…</span>
        </div>
      </div>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="providers" element={<ProvidersPage />} />
        <Route path="costs" element={<CostsPage />} />
        <Route path="cache" element={<CachePage />} />
        <Route path="rate-limits" element={<RateLimitsPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="live" element={<LiveActivityPage />} />
        <Route path="system" element={<SystemHealthPage />} />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
