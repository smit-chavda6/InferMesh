# LLM Gateway & Observability Platform

A production-shaped multi-provider LLM gateway — routes OpenAI-compatible chat
completion requests across OpenAI/Azure OpenAI, Anthropic and Gemini with
retries, fallback, caching and rate-limiting — plus a React/TypeScript
observability dashboard that runs entirely off real gateway data.

> **Build in progress.** This README is filled out fully in Phase 12 (§34).
> Current state is tracked in [`PROGRESS.md`](./PROGRESS.md).

## Repo layout

```
backend/    FastAPI gateway (Python 3.12+, uv-managed)
frontend/   React + TypeScript dashboard (Phase 10 — placeholder for now)
docker-compose.yml   local infra (postgres + redis); full stack in Phase 7
.env.example         every environment variable the stack reads
```

## Backend — local development

```bash
cd backend
uv sync                       # create venv + install deps from uv.lock
cp .env.example .env          # then fill in provider credentials

uv run uvicorn app.main:app --reload --port 8000
curl localhost:8000/health
```

### Example request

```bash
curl -sS localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say pong."}]
  }' | jq
```

The response is an OpenAI-compatible chat completion body with an added
`gateway` object (request id, provider used, cache status, fallback chain,
retries, latency).

Add `"stream": true` for Server-Sent Events — OpenAI-compatible
`chat.completion.chunk` frames, then a final frame carrying `finish_reason`,
`usage` and the `gateway` object, then `data: [DONE]`. Retry/fallback apply only
before the first token; the usage row is still written once the stream ends.

```bash
curl -N -sS localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"hi"}]}'
```

### Using an Azure OpenAI key

Set in `.env`:

```
OPENAI_MODE=azure
OPENAI_API_KEY=<azure key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT=<deployment name>
```

The request `model` field is then the Azure **deployment** name.

### Checks

```bash
cd backend
uv run ruff check .
uv run mypy
uv run pytest            # offline suite (provider calls mocked)
uv run pytest -m live    # hits real providers; needs credentials in .env
```

## Non-goals (intentionally deferred — see spec §1)

- Multi-user / RBAC for the dashboard (single-admin tool by design).
- Azure AI Foundry as a required provider (optional Phase 11 stretch).
- A generic microservices split (one backend, one frontend, Postgres, Redis).
- A general-purpose chat UI.
