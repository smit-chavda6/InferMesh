import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Loader2, LogOut, Menu, Moon, Search, Sun } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { CommandPalette } from "./CommandPalette";
import { Button } from "@/components/ui/primitives";
import { Sheet, SheetContent } from "@/components/ui/overlays";
import { useTheme } from "@/hooks/useTheme";
import { useLogout } from "@/api/queries";

export function AppLayout() {
  const { theme, toggle } = useTheme();
  const [mobileNav, setMobileNav] = useState(false);
  const [palette, setPalette] = useState(false);
  const logout = useLogout();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isMac = typeof window !== "undefined" && /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);
  const shortcutLabel = isMac ? "⌘K" : "Ctrl K";

  return (
    <div className="flex h-full relative">
      {/* Logout transition overlay */}
      {logout.isPending && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-bg/80 backdrop-blur-xs animate-in">
          <div className="flex items-center gap-2.5 rounded-lg border border-border bg-panel px-4 py-2.5 shadow-lg">
            <Loader2 className="size-4 animate-spin text-accent" />
            <span className="text-sm font-medium text-text">Signing out…</span>
          </div>
        </div>
      )}

      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[60] focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-sm focus:text-accent-fg"
      >
        Skip to content
      </a>
      <aside className="hidden w-60 shrink-0 border-r border-border bg-panel lg:block">
        <Sidebar />
      </aside>

      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent
          className="max-w-[16rem] p-0 lg:hidden"
          title="Navigation"
          description="Dashboard sections"
        >
          <Sidebar onNavigate={() => setMobileNav(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-panel px-3 sm:px-4">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileNav(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-4" />
          </Button>

          <button
            onClick={() => setPalette(true)}
            className="flex h-9 flex-1 items-center gap-2 rounded-md border border-border bg-bg-subtle px-3 text-sm text-text-faint hover:bg-bg-elevated sm:max-w-xs"
          >
            <Search className="size-4" />
            <span className="flex-1 text-left">Search…</span>
            <kbd className="rounded border border-border px-1.5 text-[10px] text-text-muted">{shortcutLabel}</kbd>
          </button>

          <div className="flex-1" />

          <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
            aria-label="Sign out"
            title="Sign out"
          >
            {logout.isPending ? (
              <Loader2 className="size-4 animate-spin text-text-muted" />
            ) : (
              <LogOut className="size-4" />
            )}
          </Button>
        </header>

        {/* tabIndex=0: doubles as the skip-link target and makes the scroll
            region keyboard-operable (axe: scrollable-region-focusable). */}
        <main
          id="main"
          tabIndex={0}
          aria-label="Main content"
          className="flex-1 overflow-y-auto outline-none focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
        >
          <div className="mx-auto max-w-[1400px] p-4 sm:p-6">
            <Outlet />
          </div>
        </main>
      </div>

      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
