"""Phase 3 through the HTTP layer: an injected provider outage triggers retry
then fallback, the request still succeeds, and the ``gateway`` metadata shows
exactly what happened.
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.errors import ProviderError, ProviderTimeoutError
from app.main import create_app

from .conftest import make_settings
from .test_routing import ScriptedAdapter

_BODY = {
    "model": "some-model",
    "messages": [{"role": "user", "content": "hi"}],
}


async def _app_client(app):  # helper
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://gateway.test")


async def test_fallback_chain_is_rendered_in_gateway_metadata() -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        app.state.registry._adapters.update(
            {
                "openai": ScriptedAdapter(
                    "openai",
                    [ProviderTimeoutError("openai", "timeout"), ProviderError("openai", "503")] * 2,
                ),
                "anthropic": ScriptedAdapter("anthropic", ["ok"]),
            }
        )
        async with await _app_client(app) as http:
            resp = await http.post("/v1/chat/completions", json=_BODY)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "hello from anthropic"

    gw = body["gateway"]
    assert gw["provider"] == "anthropic"
    assert gw["fallback"]["used"] is True
    assert gw["retries"] == 2
    chain = gw["fallback"]["chain"]
    assert [c["provider"] for c in chain] == ["openai", "anthropic"]
    assert chain[0]["outcome"] == "timeout"
    assert chain[0]["retries"] == 2
    assert chain[1]["outcome"] == "success"


async def test_all_providers_down_returns_502_with_attempts() -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        for name in ("openai", "anthropic", "gemini"):
            app.state.registry._adapters[name] = ScriptedAdapter(
                name, [ProviderError(name, "down")] * 3
            )
        async with await _app_client(app) as http:
            resp = await http.post("/v1/chat/completions", json=_BODY)

    assert resp.status_code == 502
    err = resp.json()["error"]
    assert err["type"] == "all_providers_failed"
    assert [a["provider"] for a in err["attempts"]] == ["openai", "anthropic", "gemini"]


async def test_happy_path_still_single_attempt_no_fallback() -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        app.state.registry._adapters["openai"] = ScriptedAdapter("openai", ["ok"])
        async with await _app_client(app) as http:
            resp = await http.post("/v1/chat/completions", json=_BODY)

    gw = resp.json()["gateway"]
    assert gw["fallback"]["used"] is False
    assert gw["retries"] == 0
    assert len(gw["fallback"]["chain"]) == 1
    assert gw["fallback"]["chain"][0]["outcome"] == "success"
