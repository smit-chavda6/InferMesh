"""Live end-to-end check against a real Gemini account.

Skipped unless ``GEMINI_API_KEY`` is present. Run with ``uv run pytest -m live``.
"""

from __future__ import annotations

import os

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not configured"),
]


async def test_live_gemini_roundtrip_through_gateway() -> None:
    settings = Settings()
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            resp = await http_client.post(
                "/v1/chat/completions",
                json={
                    "provider": "gemini",
                    "model": settings.gemini_default_model,
                    "messages": [{"role": "user", "content": "Reply with exactly the word: pong"}],
                    "max_tokens": 512,
                    "temperature": 0,
                },
                timeout=90.0,
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] > 0
    assert body["gateway"]["provider"] == "gemini"


async def test_live_same_call_shape_openai_and_gemini() -> None:
    """Phase 2 DoD, live: identical request body (bar provider/model) → identical shape."""
    settings = Settings()
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
