# CLAUDE.md — read this first

This repo is a **multi-session, phased build** of a multi-provider LLM gateway +
observability dashboard. Continuity across sessions depends on three files:

1. **`PROGRESS.md`** (repo root) — the running log. Per phase: the plan, what was
   done, what was skipped, deviations, and the exact verification commands + their
   output. **Read it before doing anything** to know where the build is.
2. **`docs/SPEC.md`** — the verbatim project specification. §30 has the phase list
   and each phase's Definition of Done. §0 / §0.1 are the working method and hard
   correctness guardrails. Follow the spec's decisions exactly; don't re-derive them.
3. **`git log --oneline`** — one commit per completed phase, message = `Phase N: …`.

## Where the build is (update this line when a phase completes)

**ALL 12 PHASES COMPLETE and committed.** (basic gateway → multi-provider →
reliability → persistence/cost → SSE streaming → Redis rate-limiting + caching →
production hardening → dashboard backend APIs → seed script → React/TS dashboard
UI → Azure AI Foundry provider → **polish & testing**). The build is finished;
there is no "next phase" — further work is maintenance or new feature requests.

- **Backend** (`backend/`): FastAPI async gateway, live-verified against the Azure
  + Gemini keys in `backend/.env`. **Four** providers (`openai`/azure,
  `anthropic`, `gemini`, `azure_foundry` — the Azure AI Model Inference `/models`
  API, distinct from `OPENAI_MODE=azure`). `scripts/seed.py` fills the DB with
  ~100k realistic rows. Gate: `uv run ruff check . && uv run ruff format --check .
  && uv run mypy && uv run pytest` → **156 passed / 8 skipped**.
- **Frontend** (`frontend/`, Vite + Tailwind v4 + TanStack Query + Recharts +
  Radix; branded **InferMesh**): every §6–§24 page on a real §27 endpoint through
  a thin typed client. Gate: `npx tsc -b --noEmit && npm run build && npm run lint
  && npm run test` (**28 Vitest** unit/component tests). E2E: `npx playwright
  test` (**25** — §31 journey + per-page axe a11y + perf + responsive), needs
  Postgres/Redis up and the DB seeded. Dev: `npm run dev` (proxies `/v1` +
  `/health` → `127.0.0.1:8000`).
- **CI** (`.github/workflows/ci.yml`): `backend`, `frontend`, `e2e`,
  `docker-build` jobs.
- Measured: Overview time-to-first-KPI ~0.55 s and Requests next-page ~0.15 s
  against the 100k-row seed; production bundle 246 kB gzip; a11y 0 critical/serious.

## How to work

- One phase at a time. State a 3–6 bullet plan, implement the smallest complete
  increment, run the gates, fix failures, update `PROGRESS.md`, commit, then stop
  or continue per the user.
- **Backend gate (run every backend phase, read the real output):**
  `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
- **Frontend gate (run every frontend phase):**
  `cd frontend && npx tsc -b --noEmit && npm run build && npm run lint`
- Live provider tests: `cd backend && set -a && . ./.env && set +a && uv run pytest -m live`
  (on Windows bash). They hit real Azure/Gemini; Gemini often 429s on free tier
  and those tests skip themselves — that's expected.
- Migrations: verify `alembic upgrade head` (from empty) → `alembic check` →
  `alembic downgrade base` → `alembic upgrade head`.

## Git / GitHub identity — REQUIRED

All git commits and any GitHub operations for this repo use:

- name: `smit-chavda6`
- email: `smitchavda6756@gmail.com`

Already set as this repo's local config. If it ever reads otherwise, run:
`git config user.name "smit-chavda6" && git config user.email "smitchavda6756@gmail.com"`.
Never commit under any other identity. (Keep the standard
`Co-Authored-By: Claude …` / `Claude-Session:` trailers — those are separate.)

## Local environment (survives a terminal restart)

- **Backend:** `backend/`, managed by `uv`. `cd backend && uv sync`.
- **Infra:** `docker compose up -d postgres redis` from the repo root. Postgres is
  the `pgvector/pgvector:pg16` image; an init script creates `gateway_test`.
  If Docker Desktop isn't running, start it first (Windows GUI app).
- **Secrets:** `backend/.env` (gitignored) holds the real Azure + Gemini keys.
  `.env.example` documents every variable.
- **Frontend:** `frontend/` is a placeholder until Phase 10.

## Project shape

- Monorepo: `backend/` (FastAPI, async SQLAlchemy, Redis) + `frontend/` (React/TS,
  Phase 10). Root `docker-compose.yml`, `.env.example`, `docs/SPEC.md`.
- One backend service, one frontend app, Postgres, Redis. Do **not** split into
  more services. Non-goals are listed in SPEC §1 — don't build them.
- `backend/README.md` has the backend layout and command reference.
