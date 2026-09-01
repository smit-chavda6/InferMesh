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
    <div className="grid h-full place-items-center">
      <Loader2 className="size-5 animate-spin text-text-muted" />
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
