"""Live Phase 3 demo (§33 step 4): a real OpenAI outage falls back to Gemini.

The OpenAI leg is broken by pointing it at an unroutable endpoint; the request
must still succeed via the next healthy provider in the chain, with the fallback
chain visible in the ``gateway`` metadata.

Skipped unless both OPENAI_API_KEY and GEMINI_API_KEY are configured.
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
    pytest.mark.skipif(
        not (os.getenv("OPENAI_API_KEY") and os.getenv("GEMINI_API_KEY")),
        reason="needs OPENAI_API_KEY and GEMINI_API_KEY",
    ),
]


async def test_openai_outage_falls_back_to_gemini_live() -> None:
    base = Settings()
    settings = base.model_copy(
        update={
            "azure_openai_endpoint": "https://gateway-openai-outage.invalid",
            "openai_base_url": "https://gateway-openai-outage.invalid/v1",
            "fallback_chain": ["openai", "gemini"],
            "retry_max_attempts": 2,
            "retry_base_delay_seconds": 0.1,
            "provider_attempt_timeout_seconds": 15.0,
            "cache_enabled": False,
        }
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
            resp = await http.post(
                "/v1/chat/completions",
                json={
                    "model": settings.gemini_default_model,
                    "messages": [{"role": "user", "content": "Say pong."}],
                    "max_tokens": 512,
                },
                timeout=120.0,
            )

    if resp.status_code != 200:
        err = resp.json().get("error", {})
        if "gemini:rate_limited" in str(err) or any(
            a.get("provider") == "gemini" and a.get("outcome") == "rate_limited"
            for a in err.get("attempts", [])
        ):
            pytest.skip("Gemini free-tier quota exhausted; cannot verify the fallback target")
    assert resp.status_code == 200, resp.text
    gw = resp.json()["gateway"]
    assert gw["provider"] == "gemini"
    assert gw["fallback"]["used"] is True
    providers_tried = [c["provider"] for c in gw["fallback"]["chain"]]
    assert providers_tried == ["openai", "gemini"]
    assert gw["fallback"]["chain"][0]["outcome"] in {"error", "timeout"}
