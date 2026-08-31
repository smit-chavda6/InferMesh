# Production-Grade Multi-Provider LLM Gateway & Observability Platform — SPEC

> This is the verbatim project specification. It is the source of truth for phase
> definitions (§30), Definitions of Done, and design decisions. Current build
> status lives in [`../PROGRESS.md`](../PROGRESS.md).

You are acting as a senior Python backend engineer, AI infrastructure engineer, and senior frontend
engineer, building a single cohesive portfolio project. This document is your full spec. Where this
document makes a decision, follow it exactly instead of inventing your own — that consistency is what
keeps the two halves (backend contract, frontend consumer) compatible across a long, multi-session build.

---

## 0. How to Execute This Prompt

This is a multi-week project, not a single-shot generation. Work phase by phase (see §30).

1. Maintain a `PROGRESS.md` at the repo root. Before starting a phase, write down what you're about to
   build and why. After finishing a phase, record what was done, what was skipped, and any deviation from
   this spec with a one-line justification. This is how continuity survives across separate sessions.
2. For each phase: inspect existing code → state the plan in 3-6 bullets → implement the smallest complete
   increment → run tests → fix failures → update `PROGRESS.md` → only then move to the next phase.
3. Do not jump ahead to later-phase features "while you're in there." If Phase 3 work reveals a real need
   for something scheduled in Phase 6, note it in `PROGRESS.md` and keep going — don't build it early.
4. Each phase in §30 has a **Definition of Done**. Do not mark a phase complete, and do not start the next
   one, until every item in its DoD is true and verified per the guardrails in §0.1, not assumed.

---

## 0.1 Correctness Guardrails (apply on every phase, not just at the end)

These exist because the real failure mode on a project this size isn't "can't write the code" — it's
quietly-wrong code that looks right: a schema change that updates the backend model but not the frontend
type, a provider SDK call that matches an older version of the library than what's installed, a "tests
pass" claim that was never actually run. Treat every rule below as a hard gate, not a suggestion.

1. **Verify, don't assume, for anything external.** Before calling a method on `openai`, `anthropic`,
   `google-genai`, or any other library, confirm it exists in the *installed* version — check
   `pip show <package>` / the version pinned in `package.json` and its type definitions, or the actual
   installed source — rather than relying on a remembered API shape. Provider SDKs change signatures
   across versions; your training data may reflect an older or newer one than what's installed here.
2. **Read before you write.** Never edit a file from memory of what it contained earlier in the session —
   view its current contents immediately before modifying it. Files change under you as phases progress.
3. **Prove it passes; don't assert it.** Never report "tests should pass," "this should work now," or
   "the build should succeed." Actually run `pytest`, `npm run build`, `npm test`, `mypy`, `ruff check`,
   `tsc --noEmit`, etc., read the real output, and only report success once you've seen a passing run in
   front of you. If something fails, fix it before doing anything else — don't carry a known-broken build
   forward into the next task.
4. **Lint/type errors are blocking, not cosmetic.** Run `ruff`/`mypy` (backend) and `eslint`/
   `tsc --noEmit` (frontend) as part of every phase's DoD — not deferred to Phase 12.
5. **A data-shape change is one atomic unit of work.** Any change to what a piece of data looks like must
   land together across every place it's represented: SQLAlchemy model → Alembic migration → Pydantic
   schema → API response → TypeScript type → the UI components consuming it. Before considering such a
   change complete, search the codebase for other usages of the old shape.
6. **No silent failures.** Never use a bare `except:` or otherwise swallow an exception without logging it
   with context. Never adjust a test to pass around a bug instead of fixing the underlying bug.
7. **Migrations are tested in both directions.** Before considering a migration done, run
   `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` again on a clean database — a
   migration that has only ever been upgraded once is unverified.
8. **Docker isn't done until it's run.** `docker compose up --build` from a clean checkout, using only
   values from `.env.example`, must actually succeed before Phase 7's DoD is met — don't infer this from
   the Dockerfile looking plausible.
9. **Never fabricate output.** If a command fails, an endpoint 500s, or a test doesn't exist yet, say that
   plainly in `PROGRESS.md`. Don't describe intended/expected behavior as if it were observed behavior.
10. **Checkpoint with git.** Commit once a phase's DoD is verified, with a message naming the phase (e.g.
    `Phase 4: persistence & observability`). This gives a clean point to diff against or revert to if a
    later phase turns out to have broken something earlier — don't let uncommitted work span phases.
11. **Prefer small, reviewed diffs.** Several small verifiable changes beat one large change touching many
    files at once. After each, briefly self-review the diff as if reviewing someone else's PR before
    moving on.
12. If you catch yourself about to write "this should now work" without having actually run it — stop and
    run it first. That sentence is the tell that a guardrail is about to be skipped.

---

## 1. Project Goal & Non-Goals

**Goal:** a small, real, production-shaped LLM infrastructure platform — a gateway that routes chat
completion requests across multiple LLM providers with retries/fallback/caching/rate-limiting, plus an
observability dashboard that runs entirely off real backend data.

**Explicit non-goals** (do not build these; call them out as future work in the README instead):
- Multi-user / role-based access control for the dashboard. This is a **single-admin** tool: one
  administrator manages many client "projects," each with its own API key. Do not build user
  registration, teams, or permission tiers.
- Azure AI Foundry as a required provider. It has a meaningfully different API shape from the other three
  and isn't needed to demonstrate the architecture. It is **Phase 11, optional/stretch**, not part of the
  core build, and should not appear in the core architecture diagram unless you actually implement it.
- A generic microservices platform. This is one backend service + one frontend app + Postgres + Redis.
  Do not split routing, caching, or usage-tracking into separate services.
- General-purpose chat UI ("ChatGPT clone"). The frontend is an operations/observability dashboard for
  the gateway, not a place to chat with the models.

---

## 2. Architecture

```text
                    ┌──────────────────────────┐
                    │      Client Applications   │
                    │   (any app calling the     │
                    │    gateway's chat API)     │
                    └────────────┬─────────────┘
                                 │  Authorization: Bearer <gateway client API key>
                                 ▼
                    ┌──────────────────────────┐
                    │      FastAPI Gateway      │
                    ├──────────────────────────┤
                    │ Client API-key auth        │
                    │ Request validation         │
                    │ Rate limiting              │
                    │ Semantic + exact cache     │
                    │ Provider router             │
                    │ Retry + backoff             │
                    │ Provider fallback           │
                    │ Cost calculation             │
                    │ Usage/observability logging │
                    └────────────┬─────────────┘
                                 │
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
             OpenAI          Anthropic          Gemini
                └────────────────┼────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
               PostgreSQL                  Redis
               (source of truth:           (ephemeral: rate-limit
               requests, usage,            counters, cache entries,
               costs, projects,            transient state)
               API keys, alerts)
                    │
                    ▼
          ┌──────────────────────────┐
          │ Observability Dashboard  │
          │ React + TypeScript       │
          │ (separate admin auth)    │
          └──────────────────────────┘
```

### 2.1 Key architectural decisions (do not re-derive these — follow them)

**Unified request/response contract.** `POST /v1/chat/completions` accepts an OpenAI-compatible chat
completion body (`model`, `messages`, `stream`, `temperature`, `max_tokens`, etc.). Routing is determined
by a `provider` field in the request (`"openai" | "anthropic" | "gemini"`) with `model` giving the
provider-specific model name; if `provider` is omitted, use the configured default routing/fallback chain.
Every provider adapter translates this single request shape into its own API, and translates the response
back into the same OpenAI-compatible shape, with gateway metadata (request_id, cache status, fallback
chain, provider actually used) returned in a `gateway` object alongside the standard response body — never
mixed into the `choices` array.

**Two separate auth systems — do not conflate them:**
- *Gateway client API keys* — used by client apps to call `/v1/chat/completions`. Random opaque tokens,
  stored as SHA-256 hashes, shown in full exactly once at creation, referenced afterward only by a short
  prefix (e.g. `sk-gw-7f92••••`). Sent as `Authorization: Bearer <key>`.
- *Dashboard admin auth* — a single administrator account. Bcrypt-hashed password (seeded via env var or
  a setup script), login endpoint issues a short-lived JWT delivered as an HttpOnly secure cookie, with a
  refresh flow and a logout endpoint that invalidates it. All `/v1/usage*`, `/v1/requests*`,
  `/v1/providers*`, `/v1/projects*`, `/v1/alerts*`, `/v1/system/*` read endpoints require this session.

**Cost calculation uses a versioned static pricing table** (e.g. `pricing.yaml`), listing $/1K input and
output tokens per provider+model, loaded at startup. Document in the README that this is a point-in-time
snapshot and real prices drift — don't try to fetch live pricing from providers.

**Semantic cache embeddings — pick one explicitly and document the tradeoff, don't leave it undecided:**
default to OpenAI's `text-embedding-3-small` (cheap, reuses the OpenAI client already in the project). If
`OPENAI_API_KEY` isn't configured, semantic caching degrades gracefully to **exact-match caching only**
(hash of normalized prompt + params) — don't block the whole cache feature on one provider's key being set.

**Provider health status thresholds** (trailing 5-minute window, computed from logged requests):
- `Healthy`: success rate ≥ 99%
- `Degraded`: success rate 95–99%, or 3+ consecutive failures without yet crossing the unhealthy threshold
- `Unhealthy`: success rate < 95%

**Rate limiting** is Redis-backed sliding-window per API key (not fixed-window — avoids the boundary burst
problem), with the limit/window configurable per project.

**Timestamps** are stored and computed in UTC everywhere in the backend; the frontend converts to the
viewer's local timezone for display only.

---

## 3. Backend Technology

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), PostgreSQL, Alembic, Redis, pytest, httpx,
  Docker, Docker Compose, GitHub Actions, SSE.
- Official provider SDKs: `openai`, `anthropic`, `google-genai`. Wrap each behind a common
  `ProviderAdapter` interface (`complete()`, `stream()`, `list_models()`, `health_check()`) — no
  provider-specific logic outside its adapter module.
- Repo layout: monorepo with `backend/` and `frontend/` as top-level directories, each independently
  runnable; `docker-compose.yml` at the root wires up postgres, redis, backend, and frontend for local dev.
- `.env.example` at the root documenting every required environment variable (provider keys, DB URL, Redis
  URL, JWT secret, admin bootstrap credentials) — never commit a real `.env`.

---

## 4. Frontend Technology

React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts (or an equivalent quality charting library),
TanStack Query for all server state, React Router, Lucide icons.

Separate API calls from UI components (a thin typed API client layer; components never call `fetch`
directly). Build reusable components for: cards, tables, charts, badges, filters, modals, drawers,
tooltips, loading states, error states, empty states.

---

## 5. UI Design Direction

Modern, clean, professional, information-dense but not cluttered; strong typography hierarchy; excellent
spacing; responsive; accessible; fast; recruiter-friendly. Dark-first developer-dashboard aesthetic, with a
working light mode and persisted theme choice.

Subtle animation only for: page transitions, metric updates, dropdowns, modals, status changes, loading
states. Avoid heavy gradients, glassmorphism, oversized rounded cards, or "flashy AI" visual clichés — this
should read as a serious infrastructure product, closer to Datadog/Vercel/Grafana than a consumer AI app.

---

## 6. Main Application Layout

```text
┌─────────────────────────────────────────────────────────────┐
│ Logo / LLM Gateway                              ⌘K   Theme ⚙ │
├──────────────┬──────────────────────────────────────────────┤
│ Overview     │                                              │
│ Requests     │                                              │
│ Providers    │                                              │
│ Costs        │              Main Content                    │
│ Cache        │                                              │
│ Rate Limits  │                                              │
│ API Keys     │                                              │
│ Settings     │                                              │
├──────────────┤                                              │
│ Gateway      │                                              │
│ ● Healthy    │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

Sidebar is collapsible; becomes a drawer on mobile. **The top-bar search control and the global search
palette (§21) are the same feature** — clicking the search icon or pressing `Cmd/Ctrl+K` opens the one
command-palette search UI. Don't build two separate search implementations.

---

## 7. Overview Dashboard

```text
LLM Gateway — System Overview
Last 24 hours     [1h] [24h] [7d] [30d] Custom
```

KPI cards, each backed by a real aggregation query:
- **Total Requests** — count, % change vs. previous equal-length period, sparkline.
- **Total Cost** — sum of logged cost, % change, daily trend.
- **Success Rate** — `successful / total`, with raw success/fail counts shown.
- **Average Latency** — mean, P50, P95 (computed in SQL via `percentile_cont`, not pulled client-side).
- **Fallback Rate** — `requests where fallback_used = true / total requests`.
- **Cache Hit Rate** — `cache_hits / (cache_hits + cache_misses)`.
- **Input Tokens** / **Output Tokens** — totals for the period.

---

## 8. Request Volume Chart

Time-series of requests over time, broken into successful / failed / fallback series. Range selector
(1h/24h/7d/30d) drives the aggregation bucket size server-side (e.g. per-minute for 1h, per-hour for 24h,
per-day for 7d/30d) — never send raw per-request points to the chart for the longer ranges. Hover tooltip
shows timestamp, request count, success count, error count, fallback count.

---

## 9. Provider Health Section

```text
Provider Health
OpenAI       ● Healthy     99.8%     420ms
Anthropic    ● Healthy     99.4%     510ms
Gemini       ● Degraded    96.8%     780ms
```

Per provider: health status (per the §2.1 thresholds), success rate, average latency, error rate, request
volume, fallback count — all for the selected time range.

---

## 10. Provider Comparison

Requests by provider (donut), cost by provider (bar), latency by provider (bar), error rate by provider —
all filterable by the same time-range control used elsewhere.

---

## 11. Cost Analytics Page

```text
Total Cost              $24.82
Daily Average           $3.54
Projected Monthly Cost  $106.20   (daily average × 30, clearly labeled as an estimate)
```

Charts: cost over time, cost by provider, cost by model, cost by API key/project. Filters: date range,
provider, model, API key. Breakdown table columns: Provider, Model, Input Tokens, Output Tokens, Requests,
Cost, Average Cost/Request.

---

## 12. Cost Anomaly Detection (Phase-gated, see §30 Phase 10 — optional but scoped)

If you implement this (it's explicitly optional, unlike the rest of the dashboard), keep the detection
simple and explainable: flag a project when its trailing daily cost exceeds its trailing-7-day average
daily cost by a configurable threshold (default 150%). Don't build a statistical/ML anomaly model for this
— a clear, explainable rule is more appropriate for an infra tool than a black-box one.

```text
⚠ Cost anomaly detected
Project: RAG Application
Expected daily cost: $2.40   Current: $8.90   Increase: +271%
[View affected requests →]
```

Severity: info / warning / critical, based on the size of the increase.

---

## 13. Requests Explorer

Columns: Request ID, Time, API Key, Provider, Model, Tokens, Latency, Cost, Status, Fallback, Cache.

Server-side pagination, sorting, and filtering (date range, provider, model, status, API key,
fallback-only, cache-hit-only). Search box debounced (≥300ms) before firing a request. Default page size
50, max 200 — enforce the cap server-side even if the client asks for more.

---

## 14. Request Details Drawer

Right-side drawer on row click, showing: Request ID, Status, Provider, Model, Latency, Input/Output
Tokens, Cost, Cache (HIT/MISS), Retries, Fallback (yes/no). Include a visual pipeline timeline:

```text
Request received → Validation → Rate limit check → Cache check →
Provider selected → LLM request → Response received → Usage recorded
```

For requests that used fallback, render the actual chain that happened (not a generic diagram):

```text
OpenAI → Timeout → Retry #1 → Retry #2 → Anthropic → Success
```

Never render the raw prompt/completion content in this drawer by default (see §16 on prompt privacy) —
show token counts and metadata only, with an explicit opt-in "show request/response body" toggle if you
choose to store bodies at all.

---

## 15. Provider Management Page

Cards for OpenAI, Anthropic, Gemini (and Azure AI Foundry only if you built Phase 11). Each shows:
enabled/disabled, health, available models, request count, latency, error rate, fallback count.
Configuration UI for: primary provider, fallback order, timeout, retry count, backoff settings.

Never display provider API secrets — masked status only:

```text
OpenAI            ● Enabled
API Key           ••••••••••••7f92
Primary           ✓
Fallback Priority #1
```

---

## 16. Routing Visualization

```text
Client → Router → OpenAI --(failure)--> Anthropic --(failure)--> Gemini
```

Show current primary, fallback order, live health status per node, recent failure rate. Drag-and-drop
priority reordering is nice-to-have, not required for the core build.

---

## 17. Cache Analytics Page

Cache hit rate, miss rate, estimated cost saved (hit count × average cost of a comparable non-cached
request for that model), estimated latency saved, entry count, eviction count. Charts: hit rate over time,
cost saved over time, latency saved over time.

Table columns: Cache Key (hash, never the raw prompt), Model, Created, Expires, Hits, Estimated Savings.
**Never store or display raw prompt content in the cache analytics UI** — identify entries by their hash
only, per the prompt-privacy stance in §16 above.

---

## 18. Rate Limiting Page

```text
Requests/minute   Current: 72   Limit: 100   Remaining: 28
```

Per-API-key table: Project, Limit, Current, Remaining. Visualize usage against the limit. Show recent
HTTP 429 events with timestamp and project.

---

## 19. API Keys / Projects Page

Columns: Project, API Key (masked), Created, Last Used, Requests, Cost, Rate Limit, Status. Full key value
is shown exactly once, at creation, in a dismissable "copy this now" modal — never retrievable again.
Actions: create key, revoke key, rotate key, set rate limit, view project usage. Confirmation dialog
required for revoke/rotate (destructive/irreversible actions).

---

## 20. System Health Page

```text
Gateway        ● Healthy
PostgreSQL     ● Healthy
Redis          ● Healthy
OpenAI         ● Healthy
Anthropic      ● Healthy
Gemini         ● Healthy
```

Per-dependency latency, uptime, last successful check, recent failures. Include a simple service
dependency graph (gateway → postgres/redis/providers) — this can reuse the diagram styling from §16.

---

## 21. Live Activity

Near-real-time feed via SSE (preferred; poll every 3-5s as a fallback if SSE proves troublesome):

```text
LIVE
14:32:51  OpenAI     SUCCESS    420ms
14:32:49  Anthropic  FALLBACK   812ms
14:32:47  Gemini     SUCCESS    610ms
14:32:45  OpenAI     ERROR      timeout
```

Pause/resume control. Pausing stops new rows from appearing but doesn't close the underlying connection
unnecessarily.

---

## 22. Global Search (⌘K)

Command-palette style, searching request ID, provider, model, API key/project, error type. This is the
single search entry point referenced from the top bar (§6) — do not duplicate it.

---

## 23. Notifications / Alerts

Alert types: provider degraded, provider unavailable, high error rate, cost anomaly (if built), high
latency, rate-limit spikes, Redis unavailable, PostgreSQL unavailable. Show an unread count badge.

---

## 24. Empty, Loading, and Error States

Every page needs loading skeletons, empty states, error states with a retry action. Never show a blank
screen while data loads.

```text
No requests found
Try changing your filters or date range.
[Reset Filters]
```

---

## 25. Responsive Design

Works on desktop, laptop, tablet, mobile. Desktop prioritizes density. Mobile collapses sidebar, tables
(convert to stacked cards below a breakpoint), filters (into a sheet/drawer), and charts (fewer series,
simplified axes). No unnecessary horizontal overflow.

---

## 26. Accessibility

Keyboard navigation, accessible buttons, semantic HTML, appropriate ARIA labels, visible focus states,
sufficient contrast, accessible chart tooltips where feasible.

---

## 27. Frontend API Layer

No hardcoded/fake dashboard numbers — every metric comes from a real backend endpoint. Minimum endpoint
set:

```text
GET  /v1/usage/summary
GET  /v1/usage/timeseries
GET  /v1/requests
GET  /v1/requests/{request_id}
GET  /v1/providers
GET  /v1/providers/health
GET  /v1/cache/stats
GET  /v1/rate-limits
GET  /v1/projects
GET  /v1/alerts
GET  /v1/system/health
POST /v1/auth/login
POST /v1/auth/logout
POST /v1/auth/refresh
POST /v1/projects              (create project + API key)
POST /v1/projects/{id}/rotate
POST /v1/projects/{id}/revoke
```

Design these specifically for what the dashboard renders — return pre-aggregated, dashboard-ready shapes,
not raw rows the frontend has to reduce.

---

## 28. Data Model & Storage Boundaries

PostgreSQL is the source of truth for everything persistent: requests, usage, costs, projects/API keys,
alerts. Redis is only for rate-limit counters, cache entries, and other ephemeral state — never move
persistent usage data into Redis. If semantic caching needs vector storage, use PostgreSQL + `pgvector`
before reaching for a dedicated vector database.

---

## 29. Backend Endpoints Required for the UI

Before building any UI page, inspect the backend and add whatever aggregation endpoints that page needs.
Use SQL-side aggregation (`GROUP BY`, `percentile_cont`, windowed date bucketing) — never send thousands
of raw rows to the browser for the frontend to summarize.

---

## 30. Development Phases

Each phase lists its scope and a **Definition of Done (DoD)** — don't advance until every DoD item holds.

**Phase 1 — Basic gateway.** FastAPI app, config loading, OpenAI provider adapter, provider interface,
`POST /v1/chat/completions`, `GET /health`, request-ID middleware.
*DoD:* a real request against OpenAI succeeds end-to-end via the gateway; `/health` returns 200; basic
pytest suite passes.

**Phase 2 — Multi-provider.** Anthropic, Gemini adapters; provider abstraction; router that dispatches on
the `provider` field per §2.1.
*DoD:* the same `/v1/chat/completions` call, with only `provider`/`model` changed, works against all three
providers and returns the same normalized response shape.

**Phase 3 — Reliability.** Timeout, retry with exponential backoff, fallback chain across providers.
*DoD:* a simulated provider failure (mock/injected) triggers retry then fallback, and the final response
still succeeds if a healthy provider is available; failure/retry counts are observable in logs.

**Phase 4 — Persistence & observability.** PostgreSQL, SQLAlchemy, Alembic migrations, usage logging,
token tracking, cost calculation against the pricing table (§2.1).
*DoD:* every gateway request produces exactly one row of usage data with correct tokens/cost/latency;
migrations run cleanly from empty; a stored request is queryable by ID.

**Phase 5 — Streaming.** SSE-based streaming for `/v1/chat/completions`, streaming provider abstraction,
usage capture on stream completion per §2.1's streaming/usage note.
*DoD:* a streamed request delivers incremental chunks to the client and still logs a complete, accurate
usage row once the stream ends.

**Phase 6 — Redis.** Rate limiting (sliding window, §2.1), exact-match caching, semantic caching (§2.1,
with graceful degradation if no embedding key is configured).
*DoD:* a repeated identical request is served from cache with `cache: HIT` and near-zero added latency;
exceeding a project's rate limit returns HTTP 429 with a clear error body.

**Phase 7 — Production hardening.** Docker, Docker Compose, CI (lint, type-check, test, build), input
validation, config validation on startup, health checks for all dependencies.
*DoD:* `docker compose up` brings up the full stack from a clean checkout using only `.env.example` values
filled in; CI passes on a clean PR.

**Phase 8 — Dashboard backend APIs.** Implement all endpoints in §27, all real aggregation queries, dual
auth (client API keys vs. admin JWT) per §2.1.
*DoD:* every endpoint in §27 returns real data against seeded/live data (see Phase 9) and is protected by
the correct auth scheme; unauthenticated requests to admin endpoints are rejected.

**Phase 9 — Seed / demo data.** A script (`make seed` or a compose service) that generates realistic
historical request logs — configurable volume, default ~100k rows — with plausible distributions across
providers, models, status, latency, cost, and time, so the dashboard and its performance target are
actually testable before the frontend exists.
*DoD:* seeding 100k rows completes in a reasonable time and every KPI/chart endpoint from Phase 8 returns
sensible, non-trivial numbers against it.

**Phase 10 — Advanced dashboard UI.** Application shell, overview, provider pages, requests explorer +
details drawer, cost analytics (+ optional anomaly detection, §12), cache analytics, rate limits, API
keys/projects, system health, alerts, live activity.
*DoD:* every page in this document loads real data with working loading/empty/error states; no page
contains a hardcoded number.

**Phase 11 (optional/stretch) — Azure AI Foundry provider.** Only attempt after Phase 10 is solid. Add the
adapter, update the architecture diagram and provider pages to include it, and note in `PROGRESS.md` why it
was or wasn't pursued.

**Phase 12 — Polish and testing.** Responsive design, accessibility pass, dark/light themes, animations,
frontend tests, E2E tests, performance verification against the seeded 100k-row dataset.
*DoD:* Lighthouse/axe accessibility checks pass with no critical issues; dashboard initial render stays
fast (define and record an actual number, e.g. sub-2s TTI) against the 100k-row seed; E2E suite in §31
passes.

---

## 31. Testing

**Backend:** pytest, provider mocks (never hit real provider APIs in CI), integration tests, fallback
tests, database tests, Redis tests, rate-limit tests.

**Frontend:** component tests, mocked API layer, interaction tests, routing tests.

**End-to-end (Playwright):** login → dashboard loads → request filtering → request details → cost
filtering → provider health → theme switching → live activity → API key creation/revocation → error
states.

---

## 32. Performance Requirements

Server-side pagination, database aggregation, indexed queries (index on timestamp, provider, project_id,
status at minimum), appropriate caching, lazy loading, debounced search. Target: dashboard initial render
stays fast against the 100k+ row seeded dataset from Phase 9 — measure and record the actual number, don't
just assert "fast."

---

## 33. Portfolio Demo Script

1. Open **Gateway Overview** — request volume, cost, latency, provider health all populated from real
   (seeded + live) data.
2. Send a live request from an example client script.
3. Show it appear in **Live Activity**; open its details drawer — provider, latency, tokens, cost, cache
   status all visible.
4. Simulate an OpenAI outage (env flag or mock) and send another request; show the fallback chain render
   in the details drawer, and the corresponding fallback event/alert appear in the dashboard.
5. Repeat an earlier request and show it served from cache (`cache: HIT`, near-zero latency).
6. Exceed a project's rate limit and show the 429 event on the Rate Limits page.

This sequence should make the architecture legible to a recruiter within a few minutes without narration.

---

## 34. README Requirements

Project overview, problem statement, architecture (with Mermaid diagrams), backend architecture, frontend
architecture, request lifecycle, provider abstraction, retry/fallback design, cost tracking approach
(including the pricing-table caveat from §2.1), Redis usage, PostgreSQL schema, semantic caching design
(including the embedding-model tradeoff from §2.1), dashboard screenshots, API documentation, security
notes, testing summary, actual measured performance numbers, deployment instructions, local setup, Docker
setup, example curl requests, design decisions and tradeoffs, and a "future improvements" section that
explicitly lists the non-goals from §1 (multi-tenancy, Azure AI Foundry, etc.) as intentionally deferred.

---

## 35. Engineering Rules

**Do not:**
- Hardcode fake metrics anywhere in the frontend.
- Expose provider API secrets or full client API keys after creation.
- Expose raw prompt/completion content by default (§14, §17).
- Put database logic in React components, or provider-specific logic in API route handlers.
- Create unnecessary services — one backend, one frontend, Postgres, Redis.
- Build the non-goals listed in §1.

**Do:**
- Use real backend APIs for every dashboard number.
- Keep PostgreSQL as the persistent source of truth, Redis strictly ephemeral.
- Use typed API contracts shared conceptually between backend (Pydantic models) and frontend (TS types).
- Use server-side aggregation, proper error handling, and loading/empty/error states everywhere.
- Write and run tests as you go, not as a final pass.
- Keep `PROGRESS.md` current (see §0).

---

## 36. Final Goal

A small, real LLM infrastructure platform demonstrating: multi-provider AI integration with a genuine
provider-abstraction layer; async FastAPI backend engineering with Postgres + Redis; reliability patterns
(retries, backoff, fallback, rate limiting, caching); real observability (structured logs, latency, token
usage, cost, provider health); and a React/TypeScript dashboard with real data visualization, real-time
updates, responsiveness, and accessibility — not a collection of disconnected API endpoints, and not a
frontend built against fake data.

---

## Environment notes (this machine)

- Provider credentials available: **Azure AI Foundry** (`*.services.ai.azure.com`, deployment `gpt-5.4`,
  api-version `2024-05-01-preview`) and a **Gemini** key. No native OpenAI key, no Anthropic key.
  These live in `backend/.env` (gitignored).
- The `openai` adapter is dual-mode (native | azure), switched by `OPENAI_MODE`. This keeps Azure out of
  a separate Phase 11 adapter while working with an Azure-only key.
- Gemini free tier is aggressively rate-limited; live Gemini tests skip on quota exhaustion.
- Installed SDKs are far newer than mid-2020s training data: `openai==3.x` (rides on `httpx2`),
  `anthropic==1.x` (also `httpx2`), `google-genai==2.x`. Always verify SDK shapes against the installed
  source (guardrail §0.1.1).
