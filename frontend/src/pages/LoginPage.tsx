import { useState } from "react";
import { ArrowRight, Boxes, Lock, Mail, ShieldCheck } from "lucide-react";
import { Button, Input } from "@/components/ui/primitives";
import { useLogin } from "@/api/queries";
import { ApiError } from "@/api/client";

/** Hub-and-spoke node positions in the 420×420 mesh viewBox. */
const CORE = { x: 210, y: 210 };
const NODES = [
  { pos: { x: 210, y: 58 }, color: "var(--chart-1)", label: "OpenAI" }, // top
  { pos: { x: 362, y: 210 }, color: "var(--chart-2)", label: "Anthropic" }, // right
  { pos: { x: 210, y: 362 }, color: "var(--chart-3)", label: "Gemini" }, // bottom
  { pos: { x: 58, y: 210 }, color: "var(--chart-4)", label: "Foundry" }, // left
];

function edge(a: { x: number; y: number }, b: { x: number; y: number }) {
  return `path("M ${a.x} ${a.y} L ${b.x} ${b.y}")`;
}

/** Decorative routing diagram: the gateway core with requests flowing to/from providers. */
function BrandMesh() {
  return (
    <svg
      viewBox="0 0 420 420"
      className="h-full w-full max-h-[440px] max-w-[440px] overflow-visible"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="im-core-fill" cx="50%" cy="40%" r="65%">
          <stop offset="0%" stopColor="var(--accent)" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.75" />
        </radialGradient>
        <filter id="im-blur" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="12" />
        </filter>
      </defs>

      {/* rotating outer ring */}
      <circle
        cx={CORE.x}
        cy={CORE.y}
        r="176"
        fill="none"
        stroke="var(--border-strong)"
        strokeOpacity="0.5"
        strokeWidth="1"
        strokeDasharray="2 10"
        style={{ transformOrigin: "210px 210px", animation: "im-spin-slow 48s linear infinite" }}
      />
      {/* diamond outline connecting the providers — makes it read as a mesh */}
      <polygon
        points={NODES.map((n) => `${n.pos.x},${n.pos.y}`).join(" ")}
        fill="none"
        stroke="var(--border-strong)"
        strokeOpacity="0.35"
        strokeWidth="1"
        strokeDasharray="4 7"
      />

      {/* spokes + travelling signals */}
      {NODES.map((n, i) => (
        <g key={n.label}>
          <line
            x1={CORE.x}
            y1={CORE.y}
            x2={n.pos.x}
            y2={n.pos.y}
            stroke={n.color}
            strokeOpacity="0.35"
            strokeWidth="1.5"
            strokeDasharray="3 5"
          />
          {/* request out */}
          <circle
            r="3.5"
            fill={n.color}
            className="im-signal"
            style={{ offsetPath: edge(CORE, n.pos), animationDelay: `${i * 0.55}s` }}
          />
          {/* response back */}
          <circle
            r="3"
            fill="var(--accent)"
            className="im-signal"
            style={{
              offsetPath: edge(CORE, n.pos),
              animationDirection: "reverse",
              animationDelay: `${i * 0.55 + 1.4}s`,
              animationDuration: "3.4s",
            }}
          />
        </g>
      ))}

      {/* provider nodes */}
      {NODES.map((n, i) => (
        <g
          key={`${n.label}-node`}
          style={{ animation: `im-node-float 5s ease-in-out ${i * 0.6}s infinite` }}
        >
          <circle cx={n.pos.x} cy={n.pos.y} r="7" fill="var(--panel)" stroke={n.color} strokeWidth="2" />
          <circle cx={n.pos.x} cy={n.pos.y} r="2.5" fill={n.color} />
          <text
            x={n.pos.x}
            y={n.pos.y < CORE.y ? n.pos.y - 16 : n.pos.y + 24}
            textAnchor="middle"
            className="fill-[var(--text-muted)] text-[11px] font-medium"
          >
            {n.label}
          </text>
        </g>
      ))}

      {/* pulse rings from the core */}
      {[0, 1.4].map((d) => (
        <circle
          key={d}
          cx={CORE.x}
          cy={CORE.y}
          r="26"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.5"
          style={{ transformOrigin: "210px 210px", animation: `im-pulse-ring 2.8s ease-out ${d}s infinite` }}
        />
      ))}

      {/* core: gateway */}
      <circle
        cx={CORE.x}
        cy={CORE.y}
        r="30"
        fill="var(--accent)"
        filter="url(#im-blur)"
        style={{ animation: "im-core-glow 3s ease-in-out infinite" }}
      />
      <rect
        x={CORE.x - 24}
        y={CORE.y - 24}
        width="48"
        height="48"
        rx="12"
        fill="url(#im-core-fill)"
        stroke="var(--accent)"
        strokeOpacity="0.6"
      />
      <g transform={`translate(${CORE.x - 11}, ${CORE.y - 11})`} className="text-[var(--accent-fg)]">
        <Boxes width="22" height="22" stroke="currentColor" />
      </g>
      <text
        x={CORE.x}
        y={CORE.y + 66}
        textAnchor="middle"
        className="fill-[var(--text)] text-[11px] font-semibold"
      >
        Gateway
      </text>
    </svg>
  );
}

export function LoginPage() {
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const err =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "Login failed."
        : null;

  return (
    <div className="grid min-h-full bg-bg lg:grid-cols-[1.05fr_minmax(420px,0.95fr)]">
      {/* ---- brand / routing panel (desktop) ---- */}
      <aside className="relative hidden overflow-hidden border-r border-border bg-bg-subtle lg:flex lg:flex-col lg:justify-between lg:p-10">
        <div className="pointer-events-none absolute inset-0 im-grid opacity-[0.55]" />
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 h-[560px] w-[560px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-60"
          style={{ background: "radial-gradient(circle, var(--accent-subtle), transparent 70%)" }}
        />

        <div className="relative im-rise" style={{ animationDelay: "40ms" }}>
          <div className="flex items-center gap-2.5">
            <div className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
              <Boxes className="size-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight">InferMesh</span>
          </div>
        </div>

        <div className="relative flex flex-1 items-center justify-center py-6">
          <BrandMesh />
        </div>

        <div className="relative im-rise space-y-4" style={{ animationDelay: "120ms" }}>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              One endpoint. Every model. Full visibility.
            </h2>
            <p className="mt-1 max-w-md text-sm text-text-muted">
              An OpenAI-compatible gateway that routes across providers with retries, fallback and
              caching — and a dashboard that runs entirely off real traffic.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {["4 providers", "retries + fallback", "response cache", "cost & latency analytics"].map(
              (c) => (
                <span
                  key={c}
                  className="rounded-full border border-border bg-panel px-2.5 py-1 text-text-muted"
                >
                  {c}
                </span>
              ),
            )}
          </div>
        </div>
      </aside>

      {/* ---- sign-in panel ---- */}
      <main className="flex flex-col p-6 sm:p-10">
        {/* wordmark — desktop only (the brand panel carries it on the left otherwise) */}
        <div className="hidden im-rise items-center gap-2.5 lg:flex" style={{ animationDelay: "40ms" }}>
          <div className="grid size-8 place-items-center rounded-md bg-accent text-accent-fg">
            <Boxes className="size-4" />
          </div>
          <span className="text-sm font-semibold tracking-tight">InferMesh</span>
        </div>

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-sm">
            {/* compact animated mark — mobile only */}
            <div className="relative mb-6 flex justify-center lg:hidden">
              <span
                className="absolute size-14 rounded-2xl"
                style={{
                  background: "var(--accent-subtle)",
                  animation: "im-core-glow 3s ease-in-out infinite",
                }}
              />
              <span className="relative grid size-14 place-items-center rounded-2xl bg-accent text-accent-fg">
                <Boxes className="size-6" />
              </span>
            </div>

            <div className="im-rise" style={{ animationDelay: "40ms" }}>
              <h1 className="text-xl font-semibold tracking-tight">Sign in to InferMesh</h1>
              <p className="mt-1 text-sm text-text-muted">Admin access to the gateway dashboard.</p>
            </div>

            <form
              className="im-rise mt-6 space-y-4"
              style={{ animationDelay: "110ms" }}
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate({ email, password });
            }}
          >
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-muted" htmlFor="email">
                Admin email
              </label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-faint" />
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  className="pl-9"
                  placeholder="admin@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-muted" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-faint" />
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  className="pl-9"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>

            {err && (
              <div
                role="alert"
                className="rounded-md border border-err/30 bg-err-bg px-3 py-2 text-xs text-err"
              >
                {err}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending ? (
                <>
                  <span className="size-4 animate-spin rounded-full border-2 border-accent-fg/40 border-t-accent-fg" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </form>

            <p
              className="im-rise mt-6 flex items-center gap-1.5 text-xs text-text-faint"
              style={{ animationDelay: "180ms" }}
            >
              <ShieldCheck className="size-3.5" />
              First-party session · short-lived JWT with rotating refresh
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
