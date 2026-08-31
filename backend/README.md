# Backend — LLM Gateway

FastAPI async gateway. See the repo root [`README.md`](../README.md) for setup and
[`PROGRESS.md`](../PROGRESS.md) for build status.

```bash
uv sync
docker compose -f ../docker-compose.yml up -d postgres     # Postgres + gateway_test DB
uv run alembic upgrade head                                # apply migrations
uv run uvicorn app.main:app --reload --port 8000
uv run ruff check . && uv run mypy && uv run pytest
```

## Database & migrations

- One table so far: `requests` — one row per gateway call (metadata, token usage,
  cost breakdown, fallback/retry chain, cache status). It is the observability
  source of truth the dashboard reads.
- Alembic is wired to the app's `Settings.database_url` and `Base.metadata`
  (see `alembic/env.py`). Common commands (run from `backend/`):

  ```bash
  uv run alembic upgrade head            # apply
  uv run alembic downgrade -1            # roll back one
  uv run alembic revision --autogenerate -m "message"
  uv run alembic check                   # models vs. migrations drift check
  ```

- `pytest` needs Postgres reachable (uses `TEST_DATABASE_URL`, default
  `.../gateway_test`); DB-backed tests skip with a message if it is not.

## Rate limiting & caching (Redis)

- **Rate limiting**: Redis-backed sliding-window *log* (sorted set + one atomic
  Lua script), per API key (`Authorization: Bearer sk-gw-…` → a `projects` row)
  or per anonymous IP. Over the limit → HTTP 429 with `Retry-After` and a body
  carrying `limit` / `retry_after`. `RATE_LIMIT_FAIL_OPEN=true` allows requests
  through if Redis is down.
- **Exact-match cache**: a canonicalised hash of the request (provider, model,
  messages, generation params) keys a Redis entry (`CACHE_TTL_SECONDS`). A hit
  returns `gateway.cache.status = "HIT"`, `cost_usd = 0`, and records
  `cache_saved_usd` = what the call would have cost. Streamed requests are never
  cached.
- **Semantic cache** (optional): prompt embedding → pgvector cosine nearest-
  neighbour in Postgres, above `SEMANTIC_CACHE_THRESHOLD`. Needs an OpenAI-family
  embedding key/deployment; without one it **degrades silently to exact-match
  only**.

## Seed data

`scripts/seed.py` generates realistic historical `requests` rows (weighted
providers/models, ~4.5% errors, ~3% fallback, ~20% cache hits, diurnal traffic,
real costs from `pricing.yaml`) so the dashboard is testable before the frontend
exists.

```bash
uv run python -m scripts.seed                              # ~100k rows / 30 days / 5 projects
uv run python -m scripts.seed --rows 250000 --days 45 --truncate --seed 1
# or, in Docker:
docker compose --profile seed run --rm seed --rows 100000 --truncate
```

100k rows takes ~40s. Against that dataset the overview KPI endpoints
(`/v1/usage/summary`, `/v1/usage/timeseries`, `/v1/requests`) return in
**under ~80ms server-side**.

## Cost tracking

`pricing.yaml` is a **versioned, point-in-time** price list (USD per 1K tokens),
loaded once at startup. It is never fetched live — provider prices drift. Each
`requests` row records the `pricing_version` it was costed against. Some entries
(gpt-5.x, gemini-3.x) are flagged `estimated: true`.

## Layout

```
app/
  main.py            FastAPI app factory
  config.py          pydantic-settings configuration
  logging_config.py  structlog setup
  middleware.py      pure-ASGI request-id / logging context
  errors.py          typed GatewayError hierarchy + exception handlers
  routing.py         provider Router: retry + backoff + fallback chain
  pricing.py         versioned static pricing table -> per-request cost
  observability.py   UsageRecorder: one `requests` row per call (best-effort)
  db/                Base, async engine/session, SQLAlchemy models
  schemas/           request/response + gateway-metadata + read-model contracts
  providers/         ProviderAdapter interface, per-provider adapters, registry
  api/routes/        health + /v1/chat/completions + /v1/requests/{id}
alembic/             migration environment + versions/
pricing.yaml         versioned price list (point-in-time snapshot)
tests/               pytest (provider transport mocked; -m live hits real APIs;
                     DB tests need Postgres, skip if unreachable)
```
