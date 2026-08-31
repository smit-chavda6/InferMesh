# Frontend — Observability Dashboard

React + TypeScript + Vite dashboard for the LLM gateway. Every page runs off a
real backend endpoint (spec §27); there are no mocked numbers. Built in Phase 10.

## Stack

- **Vite 8** + **React 19** + **TypeScript** (strict, `erasableSyntaxOnly`,
  `verbatimModuleSyntax` — use `import type` for type-only imports)
- **Tailwind CSS v4** (`@tailwindcss/vite`, no PostCSS config)
- **TanStack Query v5** — one hook per endpoint, in `src/api/queries.ts`
- **React Router v7**, **Recharts**, **Radix UI** primitives (shadcn-style), **cmdk** (⌘K)
- **oxlint** as the linter
- `@` path alias → `src/`

## Run it

The dashboard needs the gateway running with seed data:

```bash
# 1. infra + backend (from repo root / backend/)
docker compose up -d postgres redis
cd backend && uv run python -m scripts.seed --truncate          # ~100k demo rows
set -a && . ./.env && set +a && uv run uvicorn app.main:app --port 8000

# 2. dashboard (from frontend/)
npm install
npm run dev            # http://localhost:5173
```

The Vite dev server proxies `/v1` and `/health` to `http://127.0.0.1:8000`, so the
browser sees a single origin (first-party admin session cookie, no CORS). Log in
with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`.

> `127.0.0.1`, not `localhost`, in the proxy target — on Windows `localhost`
> resolves to `::1` first and stalls if the gateway only bound the IPv4 stack.

## Gate

```bash
npx tsc -b --noEmit && npm run build && npm run lint
```

## Layout

| Path | What |
|------|------|
| `src/api/` | `client.ts` (`apiFetch`, error envelope → `ApiError`), `types.ts` (response shapes), `queries.ts` (TanStack hooks). Components never call `fetch` directly. |
| `src/components/ui/` | Radix-backed primitives — Button, Card, Badge, Dialog, Sheet, Tabs, Table, … |
| `src/components/` | Shared building blocks — `States` (loading/empty/error), `charts`, `KpiCard`, `RangePicker`, `RequestDrawer`, … |
| `src/layout/` | `AppLayout`, `Sidebar`, `CommandPalette` (⌘K) |
| `src/pages/` | One page per spec section (Overview, Requests, Providers, Costs, Cache, Rate Limits, Projects, Alerts, Live Activity, System Health) |
| `src/hooks/` | `useTheme` (localStorage), `useRange` (URL `?range=`) |

## Production

The built SPA in `dist/` is meant to be served same-origin as the gateway (or
behind a reverse proxy that routes `/v1` + `/health` to it). Packaging it into the
compose stack is Phase 12.
