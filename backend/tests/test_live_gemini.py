"""Live end-to-end check against a real Gemini account.

Skipped unless ``GEMINI_API_KEY`` is present. Run with ``uv run pytest -m live``.
"""

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
    pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not configured"),
]


def _skip_if_gemini_quota_exhausted(resp) -> None:
    """Gemini's free tier 429s under load; the gateway then correctly falls back.
    That's not a failure of the code under test, so skip rather than fail."""
    try:
        chain = resp.json().get("gateway", {}).get("fallback", {}).get("chain", [])
        err = resp.json().get("error", {})
    except Exception:  # noqa: BLE001
        return
    if any(c.get("provider") == "gemini" and c.get("outcome") == "rate_limited" for c in chain):
        pytest.skip("Gemini free-tier quota exhausted; gateway fell back correctly")
    if "gemini:rate_limited" in str(err):
        pytest.skip("Gemini free-tier quota exhausted")


async def test_live_gemini_roundtrip_through_gateway() -> None:
    # cache off + a nonce: these tests share a real Redis with earlier runs.
    settings = Settings(cache_enabled=False)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            resp = await http_client.post(
                "/v1/chat/completions",
                json={
                    "provider": "gemini",
                    "model": settings.gemini_default_model,
                    "messages": [
                        {"role": "user", "content": f"Reply with exactly: pong [{time.time()}]"}
                    ],
                    "max_tokens": 512,
                    "temperature": 0,
                },
                timeout=90.0,
            )
    _skip_if_gemini_quota_exhausted(resp)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] > 0
    assert body["gateway"]["provider"] == "gemini"


async def test_live_same_call_shape_openai_and_gemini() -> None:
    """Phase 2 DoD, live: identical request body (bar provider/model) → identical shape."""
    settings = Settings(cache_enabled=False)
    app = create_app(settings)
    shapes = {}
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            for provider, model in [
                ("openai", settings.azure_openai_deployment or settings.openai_default_model),
                ("gemini", settings.gemini_default_model),
            ]:
                resp = await http_client.post(
                    "/v1/chat/completions",
                    json={
                        "provider": provider,
                        "model": model,
                        "messages": [{"role": "user", "content": "Say pong."}],
                        "max_tokens": 512,
                    },
                    timeout=90.0,
                )
                assert resp.status_code == 200, resp.text
                shapes[provider] = set(resp.json())

    assert (
        shapes["openai"]
        == shapes["gemini"]
        == {
            "id",
            "object",
            "created",
            "model",
            "choices",
            "usage",
            "gateway",
        }
    )
