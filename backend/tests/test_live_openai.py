"""Live end-to-end checks against a real OpenAI / Azure OpenAI account.

Skipped automatically unless ``OPENAI_API_KEY`` is present (e.g. via ``backend/.env``).
Run explicitly with::

    uv run pytest -m live
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
    pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured"),
]


def _live_settings() -> Settings:
    return Settings()  # read real environment / backend/.env


def _model_for(settings: Settings) -> str:
    if settings.openai_mode == "azure":
        assert settings.azure_openai_deployment, "AZURE_OPENAI_DEPLOYMENT must be set for Azure"
        return settings.azure_openai_deployment
    return settings.openai_default_model


async def test_live_gateway_roundtrip() -> None:
    settings = _live_settings()
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            resp = await http_client.post(
                "/v1/chat/completions",
                json={
                    "model": _model_for(settings),
                    "messages": [{"role": "user", "content": "Reply with exactly the word: pong"}],
                    "max_tokens": 10,
                    "temperature": 0,
                },
                timeout=60.0,
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] > 0
    assert body["gateway"]["provider"] == "openai"
    assert body["gateway"]["latency_ms"] > 0
