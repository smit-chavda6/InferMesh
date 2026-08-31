import { useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  Bell,
  Boxes,
  Database,
  Gauge,
  KeyRound,
  LayoutDashboard,
  ListTree,
  Search,
  ServerCog,
  Wallet,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/overlays";

const PAGES = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/requests", label: "Requests Explorer", icon: ListTree },
  { to: "/providers", label: "Providers", icon: Boxes },
  { to: "/costs", label: "Cost Analytics", icon: Wallet },
  { to: "/cache", label: "Cache Analytics", icon: Database },
  { to: "/rate-limits", label: "Rate Limits", icon: Gauge },
  { to: "/projects", label: "API Keys / Projects", icon: KeyRound },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/live", label: "Live Activity", icon: Activity },
  { to: "/system", label: "System Health", icon: ServerCog },
];

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const setOpen = (v: boolean) => {
    if (!v) setQ(""); // reset the query as the palette closes, however it was closed
    onOpenChange(v);
  };

  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  const isReqId = /^req[_-]?[a-z0-9]{4,}/i.test(q.trim());

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-xl p-0">
        <Command shouldFilter label="Global command menu" className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="size-4 text-text-faint" />
            <Command.Input
              value={q}
              onValueChange={setQ}
              autoFocus
              placeholder="Jump to a page, or paste a request ID / provider / model…"
              className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-text-faint"
            />
          </div>
          <Command.List className="max-h-80 overflow-y-auto p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-xs text-text-muted">
              No matches.
            </Command.Empty>

            {isReqId && (
              <Command.Group heading="Search">
                <Command.Item
                  value={`req ${q}`}
                  onSelect={() => go(`/requests?search=${encodeURIComponent(q.trim())}`)}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-sm data-[selected=true]:bg-bg-subtle"
                >
                  <ListTree className="size-4" />
                  Open Requests filtered by “{q.trim()}”
                </Command.Item>
              </Command.Group>
            )}

            <Command.Group heading="Pages">
              {PAGES.map((p) => (
                <Command.Item
                  key={p.to}
                  value={p.label}
                  onSelect={() => go(p.to)}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-sm data-[selected=true]:bg-bg-subtle"
                >
                  <p.icon className="size-4 text-text-muted" />
                  {p.label}
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading="Filter requests by provider">
              {["openai", "anthropic", "gemini"].map((p) => (
                <Command.Item
                  key={p}
                  value={`provider ${p}`}
                  onSelect={() => go(`/requests?provider=${p}`)}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-sm capitalize data-[selected=true]:bg-bg-subtle"
                >
                  <Boxes className="size-4 text-text-muted" />
                  {p}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
