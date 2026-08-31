"""Phase 7: startup config validation, readiness probe, input hardening."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.config import Settings

from .conftest import http_for, make_app, make_settings

_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


# --- config validation ------------------------------------------------


def test_rejects_non_asyncpg_database_url() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        make_settings(database_url="postgresql://gateway@localhost/db")


def test_rejects_bad_redis_url() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        make_settings(redis_url="http://localhost:6379")


def test_rejects_unknown_provider_in_fallback_chain() -> None:
    with pytest.raises(ValidationError, match="unknown provider"):
        make_settings(fallback_chain=["openai", "cohere"])


def test_production_requires_real_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_settings(environment="production", jwt_secret="dev-only-change-me")
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        make_settings(
            environment="production",
            jwt_secret="x" * 40,
            admin_password="admin",
        )


def test_azure_mode_needs_endpoint() -> None:
    with pytest.raises(ValidationError, match="AZURE_OPENAI_ENDPOINT"):
        make_settings(openai_mode="azure", openai_api_key="k", azure_openai_endpoint=None)


def test_startup_warnings_flag_missing_providers() -> None:
    # Explicitly clear every provider credential — `_env_file=None` disables the
    # .env file but NOT ambient os.environ, and CI sets OPENAI_API_KEY=ci-dummy etc.
    s = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://x@localhost/db",
        redis_url="redis://localhost:6379/0",
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None,
        azure_openai_endpoint=None,
        azure_foundry_api_key=None,
        azure_foundry_endpoint=None,
    )
    assert s.available_providers() == []
    warnings = s.startup_warnings()
    assert any("no LLM providers" in w for w in warnings)


# --- readiness probe -------------------------------------------------


async def test_health_is_shallow_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness_ok_when_deps_up(db_engine, redis_ready) -> None:
    async with make_app() as app, http_for(app) as http:
        resp = await http.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True
    assert body["checks"]["providers"]["ok"] is True


async def test_readiness_503_when_redis_down(db_engine) -> None:
    async with make_app(redis_url="redis://127.0.0.1:6399/0") as app, http_for(app) as http:
        resp = await http.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"]["ok"] is False


async def test_readiness_503_when_no_providers(db_engine, redis_ready) -> None:
    async with (
        make_app(openai_api_key=None, anthropic_api_key=None, gemini_api_key=None) as app,
        http_for(app) as http,
    ):
        resp = await http.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["providers"]["ok"] is False


# --- input hardening ---------------------------------------------


async def test_too_many_messages_is_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}] * 300},
    )
    assert resp.status_code == 422


async def test_oversized_body_is_413(client: AsyncClient) -> None:
    huge = {"model": "m", "messages": [{"role": "user", "content": "a" * 6_000_000}]}
    resp = await client.post("/v1/chat/completions", json=huge)
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "request_too_large"


async def test_max_tokens_upper_bound_is_422(client: AsyncClient) -> None:
    resp = await client.post("/v1/chat/completions", json={**_BODY, "max_tokens": 999_999})
    assert resp.status_code == 422
