"""Phase 2 DoD: the same /v1/chat/completions call, changing only provider/model,
works against all three providers and returns the same normalized response shape.
"""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import create_app

from .conftest import make_settings

_CASES = {
    "openai": ("gpt-4o-mini", "Hello from the OpenAI mock.", (11, 7, 18)),
    "anthropic": ("claude-3-5-sonnet-latest", "Hello from the Anthropic mock.", (13, 9, 22)),
    "gemini": ("gemini-3.6-flash", "Hello from the Gemini mock.", (6, 9, 15)),
}

_REQUIRED_KEYS = {"id", "object", "created", "model", "choices", "usage", "gateway"}


@pytest.mark.parametrize("provider", list(_CASES))
async def test_same_call_shape_across_providers(client: AsyncClient, provider: str) -> None:
    model, expected_text, (p_tok, c_tok, t_tok) = _CASES[provider]

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "provider": provider,
            "model": model,
            "messages": [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "hi"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # identical top-level shape regardless of provider
    assert set(body) == _REQUIRED_KEYS
    assert body["object"] == "chat.completion"
    assert isinstance(body["created"], int)

    choice = body["choices"][0]
    assert set(choice) == {"index", "message", "finish_reason"}
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == expected_text
    assert choice["finish_reason"] == "stop"

    assert body["usage"] == {
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": t_tok,
    }

    gateway = body["gateway"]
    assert gateway["provider"] == provider
    assert gateway["model"] == model
    assert gateway["request_id"].startswith("req_")
    assert gateway["fallback"]["used"] is False


async def test_default_provider_used_when_field_omitted(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        )
    ).json()
    assert body["gateway"]["provider"] == "openai"  # make_settings default


async def test_unconfigured_provider_is_rejected() -> None:
    """A provider with no credentials returns 503, not a 500."""
    settings = make_settings(anthropic_api_key=None)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            resp = await http_client.post(
                "/v1/chat/completions",
                json={
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-latest",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
    assert resp.status_code == 503
    assert resp.json()["error"]["type"] == "provider_not_configured"
