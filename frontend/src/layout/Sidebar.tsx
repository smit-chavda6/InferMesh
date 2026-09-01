import { NavLink } from "react-router-dom";
import {
  Activity,
  Bell,
  Boxes,
  Database,
  Gauge,
  KeyRound,
  LayoutDashboard,
  ListTree,
  ServerCog,
  Wallet,
} from "lucide-react";
import { StatusDot } from "@/components/StatusDot";
import { Logo } from "@/components/Logo";
import { useAlerts, useSystemHealth } from "@/api/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/requests", label: "Requests", icon: ListTree },
  { to: "/providers", label: "Providers", icon: Boxes },
  { to: "/costs", label: "Costs", icon: Wallet },
  { to: "/cache", label: "Cache", icon: Database },
  { to: "/rate-limits", label: "Rate Limits", icon: Gauge },
  { to: "/projects", label: "API Keys", icon: KeyRound },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/live", label: "Live Activity", icon: Activity },
  { to: "/system", label: "System Health", icon: ServerCog },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const health = useSystemHealth();
  const alerts = useAlerts();
  const gwStatus = health.data?.gateway.status ?? "unknown";
  const unread = alerts.data?.unread_count ?? 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 px-4">
        <div className="grid size-7 place-items-center rounded-md bg-accent text-accent-fg">
          <Logo className="size-5" />
        </div>
        <span className="text-sm font-semibold tracking-tight">InferMesh</span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                isActive
                  ? "bg-accent-subtle text-text font-medium"
                  : "text-text-muted hover:bg-bg-subtle hover:text-text",
              )
            }
          >
            <Icon className="size-4 shrink-0" />
            <span className="flex-1">{label}</span>
            {to === "/alerts" && unread > 0 && (
              <span className="grid min-w-5 place-items-center rounded-full bg-err px-1 text-[10px] font-semibold text-white">
                {unread}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border px-4 py-3">
        <div className="text-[11px] uppercase tracking-wide text-text-faint">Gateway</div>
        <div className="mt-1 flex items-center gap-2 text-sm capitalize">
          <StatusDot status={gwStatus} pulse />
          {gwStatus}
        </div>
      </div>
    </div>
  );
}
