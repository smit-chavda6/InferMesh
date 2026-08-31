# PROGRESS

Continuity log for the multi-phase build. One section per phase: the plan before
starting, then what was actually done / skipped / deviated after finishing.

Phase list and Definitions of Done live in the project spec (§30). Guardrails in
§0.1 are hard gates — "verified" below means a command was run and its output read,
not assumed.

---

## Environment (recorded 2026-08-31)

| Tool   | Version            |
|--------|--------------------|
| Python | 3.13.5             |
| Node   | 22.16.0            |
| npm    | 11.16.0            |
| Docker | 29.2.1             |
| uv     | 0.11.6             |
| git    | 2.51.2             |

Backend dependency manager: **uv** (`backend/pyproject.toml` + `backend/uv.lock`).

### Provider credentials available
- **Azure AI Foundry** resource (`*.services.ai.azure.com`), deployment `gpt-5.4`,
  api-version `2024-05-01-preview`. In `backend/.env` (gitignored). **Live-verified.**
- **Gemini** key in `backend/.env` (gitignored). Format `AQ.*` (not the classic
  `AIza*` AI Studio shape) — to be validated in Phase 2.
- No native OpenAI key, no Anthropic key.

### Azure AI Foundry integration facts (verified live 2026-08-31)
- The OpenAI SDK's `AsyncAzureOpenAI(azure_endpoint="https://<res>.services.ai.azure.com",
  api_version="2024-05-01-preview", api_key=...)` works against this Foundry resource.
  The `/api/projects/<project>` suffix from the portal is the `azure-ai-projects`
  path and is **not** used for the OpenAI data plane — strip it.
- `gpt-5.4` **rejects `max_tokens`** with `unsupported_parameter` and requires
  `max_completion_tokens`. The OpenAI adapter now translates
  `max_tokens -> max_completion_tokens` so the gateway's public contract stays
  OpenAI-classic. `temperature` is accepted.

### Notable installed-library facts (verified against installed source, per §0.1.1)
- `openai==3.6.0` — a major version well beyond the 1.x era. Talks over **`httpx2`**,
  not `httpx`, so tests mock via `httpx2.MockTransport`. Core surface unchanged:
  `AsyncOpenAI` / `AsyncAzureOpenAI`, `client.chat.completions.create(model=, messages=)`
  returning `ChatCompletion` with `.choices[].message`, `.usage.{prompt,completion,total}_tokens`.
  Error classes (`APITimeoutError`, `RateLimitError`, `AuthenticationError`,
  `BadRequestError`, `APIStatusError`, `APIConnectionError`) all present.
  `AsyncAzureOpenAI(azure_endpoint=, api_version=, api_key=)`.
- `fastapi==0.141.x` — `include_router` produces a lazy `_IncludedRouter` in
  `app.routes`; routes still resolve normally (proven by tests). Cosmetic only.

---

## Phase 1 — Basic gateway

**Status: COMPLETE — all DoD items verified, including the live end-to-end call.**

### Plan (pre-phase)
- Monorepo skeleton: `backend/` (uv), `frontend/` placeholder, root `.env.example`,
  `.gitignore`, `docker-compose.yml` (infra only for now).
- Backend: FastAPI app factory, `pydantic-settings` config with light startup
  validation, structlog structured logging, pure-ASGI request-ID middleware.
- `ProviderAdapter` ABC (`complete` / `stream` / `list_models` / `health_check`) +
  normalized dataclasses. `stream` raises `NotImplementedError` until Phase 5.
- OpenAI adapter, **dual-mode native | azure** (config-switched, one adapter).
- `POST /v1/chat/completions` (OpenAI-compatible body; `gateway` metadata object
  beside `choices`, never inside it). `GET /health` (liveness only).
- Tests: pytest with `httpx2.MockTransport`-mocked provider + a `live`-marked
  end-to-end test skipped without `OPENAI_API_KEY`. Gates: `ruff`, `mypy`.

### Done (post-phase)
- Files: `backend/app/{config,logging_config,middleware,errors,main}.py`,
  `backend/app/schemas/{chat,gateway}.py`,
  `backend/app/providers/{base,openai_adapter,registry}.py`,
  `backend/app/api/routes/{health,chat}.py`.
- Tests: `backend/tests/{conftest,test_health,test_chat,test_openai_adapter,test_live_openai}.py`.
- Response contract: OpenAI-compatible body + `gateway` object
  (`request_id`, `provider`, `model`, `upstream_model`, `cache`, `fallback`,
  `retries`, `latency_ms`, `cost_usd` placeholder).
- Request-ID middleware: accepts inbound `X-Request-ID`, else generates `req_<hex>`;
  echoes it in the response header and binds it to the structlog context.
- Errors surface as `{"error": {"type", "message", "request_id"}}`; provider
  failures mapped to typed `GatewayError` subclasses with sane HTTP statuses.

### Verified (commands run, output read)
- `uv run ruff check .` → **All checks passed**
- `uv run ruff format --check .` → clean
- `uv run mypy` (scope: `app/`, `strict = true`) → **Success: no issues found in 17 source files**
- `uv run pytest` (offline) → **15 passed, 1 skipped** (live test skipped when
  `OPENAI_API_KEY` is not exported — keeps the offline suite hermetic)
- `uv run pytest -m live` (env from `backend/.env`) → **1 passed** —
  `test_live_gateway_roundtrip` drove a real request through the full ASGI app
  (middleware → router → Azure adapter → live `gpt-5.4`) and got a valid
  completion + non-zero token usage + `gateway.provider == "openai"`.
- `/health` returns 200 (asserted in `test_health`).

### Deviations from spec (with justification)
1. **Adapter is dual-mode native/Azure OpenAI** instead of native-only. Spec puts
   Azure at Phase 11 (optional), but the only OpenAI-family credential available is
   Azure. Same SDK, same adapter, one `OPENAI_MODE` switch — no separate Azure
   adapter, no new architecture surface. Native OpenAI path is fully implemented
   and covered by mocked tests; it just lacks a live key. Anthropic/Gemini live
   calls remain out of scope until Phase 2 + keys.
2. **mypy scoped to `app/`**, not `tests/`. Test modules intentionally pass
   wrong-typed inputs to exercise validation/error mapping; strict typing there
   fights the tests. Tests are still linted by `ruff`.
3. **`docker-compose.yml` ships infra only** (postgres + redis) this phase. Backend
   and frontend services are added in Phase 7 per the spec's phase ordering.

### Noted for later (do NOT build early)
- `BaseHTTPMiddleware` buffers streaming responses — already avoided by writing the
  request-context middleware as pure ASGI. Relevant when Phase 5 adds SSE.
- Azure `models.list()` may behave differently from native for `health_check()`;
  revisit in Phase 7/20 system-health work.

---

## Phase 2 — Multi-provider

**Status: COMPLETE — DoD verified (2/3 providers live, all 3 via the same normalized
shape; Anthropic live leg pending a key, same honest gap as Phase 1's native OpenAI).**

### Plan (pre-phase)
- Add `anthropic` + `google-genai` SDKs (verify installed API shapes first).
- `AnthropicAdapter` and `GeminiAdapter` implementing the full `ProviderAdapter`
  interface; translation logic lives only in the adapter (+ a tiny shared
  `_common.py` for system-prompt hoisting / content flattening).
- Register both in `ProviderRegistry._BUILDERS`; router already dispatches on the
  request `provider` field (`resolve()`), default when omitted.
- Tests: transport-mocked (httpx2) for Anthropic like OpenAI; boundary-mocked for
  Gemini (heavier transport stack). A parametrized gateway test asserting the
  three providers return a byte-identical top-level response shape. Live tests for
  Gemini + a cross-provider shape check.

### Done (post-phase)
- `backend/app/providers/anthropic_adapter.py`, `gemini_adapter.py`, `_common.py`.
- Registry builds all three lazily; `Settings` gained `anthropic_*` / `gemini_*`
  knobs, `provider_enabled()` and a 3-provider `available_providers()`.
- All adapters' `complete()` now guarantee a typed `GatewayError` on any failure
  (SDK base error mapped, plus a catch-all that logs + re-raises as `ProviderError`)
  — Phase 3's fallback logic can rely on that.
- Translation specifics:
  - **Anthropic**: system messages hoisted to top-level `system`; `max_tokens`
    required, so request value or `ANTHROPIC_DEFAULT_MAX_TOKENS` (1024); `stop` →
    `stop_sequences`; `stop_reason` → OpenAI `finish_reason`.
  - **Gemini**: system → `config.system_instruction`; `assistant` role → `model`;
    `max_tokens` → `max_output_tokens`; automatic function calling disabled;
    `completion_tokens = total - prompt` so **thinking tokens are counted**
    (Gemini 3.x thinks by default); blocked responses yield `content=None` +
    `finish_reason="content_filter"` rather than an error.

### Verified (commands run, output read)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy` (strict, `app/`) → **no issues found in 20 source files**
- `uv run pytest` (offline) → **34 passed, 3 skipped** (skips = live)
- `uv run pytest -m live` (env from `backend/.env`) → **3 passed**:
  - `test_live_openai_roundtrip` — real Azure `gpt-5.4`
  - `test_live_gemini_roundtrip_through_gateway` — real `gemini-3.6-flash`
  - `test_live_same_call_shape_openai_and_gemini` — **same request body, only
    provider/model changed, produced the identical top-level key set** across
    Azure OpenAI and Gemini (the Phase 2 DoD, live).
- `test_same_call_shape_across_providers[openai|anthropic|gemini]` (mocked) —
  all three return `{id, object, created, model, choices, usage, gateway}` with
  matching `choice`/`usage` structure.

### Provider facts discovered (verified live 2026-08-31)
- **Gemini key** works (auth OK). Model landscape has moved well past training
  data: `gemini-2.0-flash` / `2.5-flash` / `1.5-flash` all return 404 "no longer
  available"; current default chosen = **`gemini-3.6-flash`**. `google-genai`
  `HttpOptions.timeout` is **milliseconds**; it has its own tenacity retry loop,
  pinned to `attempts=1` so the gateway owns retries.
- Gemini 3.x models **think by default** — with a small `max_output_tokens` the
  visible text can be empty (`finish_reason=MAX_TOKENS`) while `thoughts_token_count`
  is spent. Live tests use `max_tokens: 512`.
- `anthropic==1.2.0` also rides on `httpx2`; `client.models.list()` exists.

### Deviations from spec (with justification)
1. **Anthropic live call not verified** — no API key available. Adapter is fully
   implemented and covered by transport-mocked tests proving request translation
   and the normalized response shape. Closing this needs `ANTHROPIC_API_KEY` in
   `backend/.env`, then `uv run pytest -m live` (a live Anthropic test mirroring
   `test_live_gemini` should be added at that point).
2. Gemini adapter is **boundary-mocked** in unit tests (patching
   `client.aio.models.generate_content`) rather than transport-mocked. The SDK's
   async transport stack is more involved than a single httpx client; the
   translation code (`_build_contents`/`_build_config`/`_usage`) still executes
   against a constructed response, and the live tests exercise the real transport.

---

## Phase 3 — Reliability

**Status: COMPLETE — DoD verified with injected failures (unit + HTTP layer) and
live (real OpenAI outage → Gemini fallback).**

### Plan (pre-phase)
- New `app/routing.py` with a `Router` owning retry + backoff + fallback (not in
  adapters, not in the route handler).
- Per-provider retry loop (`retry_max_attempts`), exponential backoff with jitter,
  retry only on retryable outcomes (timeout / rate-limit / upstream error); stop
  immediately on `bad_request`.
- On a provider being exhausted, advance through an ordered provider chain; if all
  fail, raise `AllProvidersFailedError` carrying the full `ProviderAttempt` log.
- Hard per-attempt ceiling via `asyncio.wait_for` (backstop for a hung SDK call).
- Wire into `main.py` lifespan (`app.state.router`) and the chat route; populate
  `gateway.fallback.{used,chain}` and `gateway.retries` from the attempt log.

### Done (post-phase)
- `app/routing.py`: `Router`, `ExecutionResult`, `_backoff_delay`, `_provider_chain`.
  Injectable `sleep` for deterministic tests.
- `Settings`: `retry_max_attempts`, `retry_base_delay_seconds`,
  `retry_max_delay_seconds`, `retry_backoff_multiplier`, `retry_jitter`,
  `provider_attempt_timeout_seconds`, `fallback_enabled`, `fallback_chain` (JSON
  list in env), `fallback_on_explicit_provider`.
- `AllProvidersFailedError` now carries `attempts`; the error handler renders them
  under `error.attempts` in the 502 body.
- `gateway.fallback.chain` is always populated (1+ entries) — the "what actually
  happened" log the details drawer (§14) renders; `fallback.used` is true only
  when >1 distinct provider was tried.

### Design decisions
- **`bad_request` (upstream 4xx) is not retried and does not fall back** — it is
  treated as a caller error that would fail on every provider; fail fast with the
  original `ProviderBadRequestError` (400). `auth`/`not_configured` likewise are
  not retryable. Retryable: `timeout`, `rate_limited`, generic `error` (5xx / conn).
- **Explicit `provider` still falls through** the rest of the chain by default
  (`fallback_on_explicit_provider=true`) so the demo works with or without the
  field; set false to make a named provider a hard directive.
- Adapters run with **SDK retries disabled** (`max_retries=0` / `attempts=1`); the
  gateway is the single owner of retry policy.

### Verified (commands run, output read)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy` (strict, `app/`) → **no issues found in 21 source files**
- `uv run pytest` (offline) → **46 passed, 3 skipped**. New:
  `tests/test_routing.py` (10 cases: retry-then-succeed, exponential-backoff
  growth+cap, fallback to next provider, rate-limit retryable, bad-request no
  retry/no fallback, all-providers-fail aggregate, explicit-provider fallback
  on/off, hard-timeout ceiling) and `tests/test_reliability_api.py` (3 cases
  through the HTTP layer asserting `gateway.fallback.chain`, a 502 with
  `error.attempts`, and the untouched happy path).
- `uv run pytest -m live` → **4 passed**, incl.
  `test_openai_outage_falls_back_to_gemini_live`: OpenAI pointed at an
  unroutable host, request still succeeded via real `gemini-3.6-flash`, and
  `gateway.fallback.chain == ["openai" (error), "gemini" (success)]`.

---

## Phase 4 — Persistence & observability

**Status: COMPLETE — all DoD items verified (offline + live), migrations tested
up/down/up and `alembic check`-clean.**

### Infra
- `docker compose up -d postgres` → Postgres 16. `docker-compose.yml` mounts
  `infra/postgres/init-test-db.sh` which creates `gateway_test` on first volume
  init. (Docker Desktop had to be started; first `up` got orphaned by a Docker
  restart — a re-`up` fixed it.)
- Deps added: `sqlalchemy[asyncio]` 2.0.52, `asyncpg` 0.31, `alembic` 1.19.

### Plan (pre-phase)
- `app/db/`: declarative `Base` with a constraint-naming convention (makes
  Alembic downgrade reliable), async engine + sessionmaker in a `Database` object
  owned by the lifespan, `get_session` dependency.
- One table, `requests` = observability source of truth (request + usage + cost +
  fallback chain + cache status), indexed on created_at/provider/model/status/
  fallback_used/cache_status/cost_usd/error_type/api_key_prefix.
- `pricing.yaml` (versioned) + `PricingTable` loader with model-match precedence
  (exact → date-suffix-stripped → longest prefix → provider default → none).
- `UsageRecorder`: exactly one row per request on both success and error paths;
  best-effort (a DB failure is logged, never turned into a 500).
- `GET /v1/requests/{request_id}` (no auth yet — Phase 8) for "queryable by id".
- Alembic async env reading URL from `Settings`; autogenerate + up/down/up cycle.

### Done (post-phase)
- `app/db/{base,session,models}.py`, `app/pricing.py`, `app/observability.py`,
  `app/schemas/observability.py`, `app/api/routes/requests.py`.
- `backend/pricing.yaml` — version `2026-08-31`; covers the live models
  (`gpt-5.4`, `gemini-3.6-flash`, `claude-3-5-sonnet-*`) plus common ones; some
  entries flagged `estimated: true` where no public list price was on hand.
- `alembic/` (async template, env rewired to `Settings` + `Base.metadata`,
  `compare_type`/`compare_server_default` on) + `versions/83a048a6c618_*.py`.
- Chat route restructured: `try/except GatewayError/finally`, builds a
  `RequestOutcome` on every path, records it in `finally`.
- Lifespan now owns `Database`, `PricingTable`, `UsageRecorder`; disposes the
  engine on shutdown; logs `database_reachable` + `pricing_version` at startup.
- `Settings`: `database_url`, `db_echo`, `db_pool_size`, `db_max_overflow`,
  `usage_logging_enabled`.

### Verified (commands run, output read)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy` (strict, `app/`) → **no issues, 29 source files**
- `uv run pytest` → **61 passed, 4 skipped** (DB tests ran against Postgres).
  New: `tests/test_pricing.py` (10) and `tests/test_persistence.py` (5:
  exactly-one-row on success, cost from pricing table, queryable-by-id + 404,
  exactly-one-row on all-providers-fail with the error fields + chain, and
  recorder failure does **not** break the 200).
- Migrations: `alembic upgrade head` from a **dropped/empty** DB → OK;
  `alembic check` → **"No new upgrade operations detected"** (models ⇄ migration
  in sync); `downgrade base → upgrade head` cycle → OK.
- **Live**: `pytest -m live` (4 passed) wrote real rows to the `gateway` DB —
  verified by `psql`: e.g. Azure `gpt-5.4` (upstream `gpt-5.4-2026-03-05`),
  tokens 13/5/18, `cost_usd 0.000066` = input `0.000016` + output `0.000050`,
  `pricing_version 2026-08-31`, real `latency_ms ~2587`. Gemini rows show
  thinking tokens folded into `completion_tokens` and costed.

### Deviations / decisions
1. **No `projects` table yet.** `api_key_prefix` is a nullable string until
   Phase 6 adds API keys + rate limits; that migration will add the FK atomically
   then. Avoids building auth ahead of its phase while keeping the `requests`
   shape stable.
2. **Single `requests` table** (not separate `requests` + `usage`) — the
   dashboard's Requests Explorer (§13) maps 1:1 onto it and every aggregation is
   a single-table `GROUP BY`.
3. **DB-backed tests require Postgres**, and `pytest` now needs it for the full
   suite. They **skip with a message** if `TEST_DATABASE_URL` is unreachable, so
   the suite still runs (partially) without Docker; CI (Phase 7) provides it.
4. `pricing.yaml` estimates for `gpt-5.x` / `gemini-3.x` are marked
   `estimated: true` and surfaced via `CostBreakdown.estimated` — README will
   carry the point-in-time caveat (§34).

### Noted for later
- Test suite is ~37s now (per-test `create_all`/`drop_all` + `genai.Client`
  construction). Phase 12 perf pass: consider a session-scoped schema + per-test
  truncate, and a shared mocked Gemini client.
- `/v1/requests/{id}` currently unauthenticated — Phase 8 puts it behind admin JWT.

---

## Phase 5 — Streaming

**Status: COMPLETE — DoD verified offline (mocked SSE for all 3 providers) and
live (real SSE from Azure `gpt-5.4` + `gemini-3.6-flash`, each logging one
accurate `streamed=true` row).**

### Plan (pre-phase)
- Implement `ProviderAdapter.stream()` on all three adapters (was
  `NotImplementedError`), yielding `StreamChunk`s; usage/finish arrive on the
  final chunk(s).
- `Router.execute_stream()` — retry + fallback apply **only before the first
  token**; after that a failure ends the stream with a terminal `StreamOutcome`
  carrying `error`. Yields `StreamChunk`s then exactly one `StreamOutcome`.
- Chat route: `stream=true` → `StreamingResponse` of OpenAI-compatible
  `chat.completion.chunk` SSE frames; final frame carries `finish_reason`,
  `usage` and the `gateway` object; then `data: [DONE]`. A pre-stream failure is
  a JSON 502 (no SSE body started); a mid-stream failure ends with an error in
  the `gateway` object + `[DONE]`.
- Usage row recorded in the generator's `finally` (survives client disconnect),
  `streamed=true`.

### Done (post-phase)
- `StreamChunk` gained `response_id` / `created` / `model` (populated on
  whichever provider chunks include them).
- `openai_adapter.stream`: `stream=True` + `stream_options={"include_usage":true}`;
  maps delta/finish/usage chunks.
- `anthropic_adapter.stream`: raw event stream — `message_start` (input tokens),
  `content_block_delta` (text), `message_delta` (stop_reason + output tokens).
- `gemini_adapter.stream`: `generate_content_stream` (`await` → async iterator);
  per-part `.text` delta, final part `.usage_metadata` + finish reason. Blocked
  parts that raise on `.text` are tolerated.
- `routing.py`: `StreamOutcome` dataclass + `Router.execute_stream`.
- `api/routes/chat.py` restructured: non-stream path returns
  `JSONResponse(jsonable_encoder(..., exclude_none=True))`; `_stream_response`
  pulls the first item eagerly so a pre-stream failure is a clean JSON error,
  then returns the `StreamingResponse`. Shared `_apply_error` / `_finalize_outcome`.
- Pure-ASGI request-context middleware (Phase 1 choice) passes SSE through
  untouched — no rework needed.

### Verified (commands run, output read)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy` (strict, `app/`) → **no issues, 29 source files**
- `uv run pytest` (offline) → **68 passed, 6 skipped**. New:
  `tests/test_streaming.py` (8: router deltas+terminal, fallback-before-first-
  token, mid-stream-failure-no-fallback, SSE shape + `[DONE]` + final
  usage/gateway, one accurate `streamed=true` row, pre-stream failure = JSON 502
  + error row, mid-stream failure = error row). Adapter `stream()` unit tests
  rewritten for all three (were `NotImplementedError` asserts).
- **Live**: `pytest -m live` → **6 passed** incl. `test_live_stream_openai`
  (Azure `gpt-5.4`) and `test_live_stream_gemini`. `psql` confirms
  `streamed=true` rows: Gemini 7/190/197 tokens `cost_usd 0.000477` `finish=stop`;
  OpenAI 12/7/19 `cost_usd 0.000085`.

### Decisions
1. **No streaming recovery after first byte.** Standard SSE constraint — you
   can't un-send bytes. Retry/fallback happen only while buffering for the first
   token; after that a failure yields a terminal `StreamOutcome.error`, the SSE
   ends with the error surfaced in the `gateway` object, and the row is
   `status="error"` with whatever partial usage was seen.
2. **`gateway` object rides on the final SSE frame** (next to `usage`), not a
   separate `event:` — keeps a single parse path and matches how OpenAI attaches
   `usage` to a terminal chunk.
3. Mock strategy for streaming: OpenAI + Anthropic get real SSE bytes through
   `httpx2.MockTransport` (branch on `"stream": true` in the request body);
   Gemini stays boundary-mocked (`generate_content_stream` patched to return an
   async iterator of constructed partials).
