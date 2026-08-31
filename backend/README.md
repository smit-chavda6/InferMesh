# Backend — LLM Gateway

FastAPI async gateway. See the repo root [`README.md`](../README.md) for setup and
[`PROGRESS.md`](../PROGRESS.md) for build status.

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run ruff check . && uv run mypy && uv run pytest
```

## Layout

```
app/
  main.py            FastAPI app factory
  config.py          pydantic-settings configuration
  logging_config.py  structlog setup
  middleware.py      pure-ASGI request-id / logging context
  errors.py          typed GatewayError hierarchy + exception handlers
  schemas/           request/response + gateway-metadata contracts
  providers/         ProviderAdapter interface, per-provider adapters, registry
  api/routes/        health + /v1/chat/completions
tests/               pytest (provider transport mocked; -m live hits real APIs)
```
