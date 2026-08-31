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
