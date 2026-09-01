import { lazy, Suspense } from "react";
import type { ComponentType, ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AppLayout } from "@/layout/AppLayout";
import { LoginPage } from "@/pages/LoginPage";
import { Skeleton } from "@/components/ui/primitives";
import { useAuthMe } from "@/api/queries";

// Route-level code splitting — each page (and the chart lib it pulls in) is its
// own chunk, loaded on first navigation.
function lazyPage<M extends Record<string, unknown>, K extends keyof M>(
  factory: () => Promise<M>,
  key: K,
) {
  return lazy(async () => ({ default: (await factory())[key] as ComponentType }));
}

const OverviewPage = lazyPage(() => import("@/pages/OverviewPage"), "OverviewPage");
const RequestsPage = lazyPage(() => import("@/pages/RequestsPage"), "RequestsPage");
const ProvidersPage = lazyPage(() => import("@/pages/ProvidersPage"), "ProvidersPage");
const CostsPage = lazyPage(() => import("@/pages/CostsPage"), "CostsPage");
const CachePage = lazyPage(() => import("@/pages/CachePage"), "CachePage");
const RateLimitsPage = lazyPage(() => import("@/pages/RateLimitsPage"), "RateLimitsPage");
const ProjectsPage = lazyPage(() => import("@/pages/ProjectsPage"), "ProjectsPage");
const AlertsPage = lazyPage(() => import("@/pages/AlertsPage"), "AlertsPage");
const LiveActivityPage = lazyPage(() => import("@/pages/LiveActivityPage"), "LiveActivityPage");
const SystemHealthPage = lazyPage(() => import("@/pages/SystemHealthPage"), "SystemHealthPage");

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

function PageFallback() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-56" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[104px]" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

/** Each lazy page mounts inside AppLayout's <Suspense>; wrap here too so the
 *  boundary is per-element and React shows the fallback on every navigation. */
const suspend = (el: ReactNode) => <Suspense fallback={<PageFallback />}>{el}</Suspense>;

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={suspend(<OverviewPage />)} />
        <Route path="requests" element={suspend(<RequestsPage />)} />
        <Route path="providers" element={suspend(<ProvidersPage />)} />
        <Route path="costs" element={suspend(<CostsPage />)} />
        <Route path="cache" element={suspend(<CachePage />)} />
        <Route path="rate-limits" element={suspend(<RateLimitsPage />)} />
        <Route path="projects" element={suspend(<ProjectsPage />)} />
        <Route path="alerts" element={suspend(<AlertsPage />)} />
        <Route path="live" element={suspend(<LiveActivityPage />)} />
        <Route path="system" element={suspend(<SystemHealthPage />)} />
        <Route path="*" element={suspend(<OverviewPage />)} />
      </Route>
    </Routes>
  );
}
