"""Live Phase 6: real cache HIT (Azure) + a real 429 from the sliding-window limiter."""

from __future__ import annotations

import os
import time

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured"),
]


def _model(s: Settings) -> str:
    return (s.azure_openai_deployment if s.openai_mode == "azure" else s.openai_default_model) or ""


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")


async def _flush_ratelimit(settings: Settings) -> None:
    """Clear stale sliding-window buckets from earlier live runs (real Redis db)."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        keys = await client.keys("ratelimit:*")
        if keys:
            await client.delete(*keys)
    finally:
        await client.aclose()


async def test_live_repeated_request_hits_cache() -> None:
    settings = Settings(cache_enabled=True, semantic_cache_enabled=False)
    body = {
        "provider": "openai",
        "model": _model(settings),
        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
        "max_tokens": 10,
        "temperature": 0,
    }
    app = create_app(settings)
    async with LifespanManager(app), await _client(app) as http:
        # flush this request's key space is impractical; just use a unique nonce
        body["messages"][0]["content"] += f" [{time.time()}]"
        first = await http.post("/v1/chat/completions", json=body, timeout=60)
        t0 = time.perf_counter()
        second = await http.post("/v1/chat/completions", json=body, timeout=60)
        hit_ms = (time.perf_counter() - t0) * 1000

    assert first.json()["gateway"]["cache"]["status"] == "MISS"
    g2 = second.json()["gateway"]
    assert g2["cache"]["status"] == "HIT"
    assert g2["cost_usd"] == 0.0
    assert hit_ms < 150  # served from Redis, not the provider
    assert (
        first.json()["choices"][0]["message"]["content"]
        == (second.json()["choices"][0]["message"]["content"])
    )


async def test_live_rate_limit_429() -> None:
    settings = Settings(rate_limit_enabled=True, rate_limit_anon_per_minute=2, cache_enabled=False)
    await _flush_ratelimit(settings)
    body = {
        "provider": "openai",
        "model": _model(settings),
        "messages": [{"role": "user", "content": f"hi [{time.time()}]"}],
        "max_tokens": 5,
    }
    app = create_app(settings)
    async with LifespanManager(app), await _client(app) as http:
        codes = [
            (await http.post("/v1/chat/completions", json=body, timeout=60)).status_code
            for _ in range(2)
        ]
        blocked = await http.post("/v1/chat/completions", json=body, timeout=60)

    assert codes == [200, 200]
    assert blocked.status_code == 429
    assert blocked.json()["error"]["type"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1
