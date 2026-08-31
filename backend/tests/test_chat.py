from __future__ import annotations

from httpx import AsyncClient

_BODY = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "hi"}],
}


async def test_chat_completion_happy_path(client: AsyncClient) -> None:
    resp = await client.post("/v1/chat/completions", json=_BODY)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["choices"][0]["message"]["content"] == "Hello from the mock provider."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}

    gateway = body["gateway"]
    assert gateway["provider"] == "openai"
    assert gateway["model"] == "gpt-4o-mini"
    assert gateway["upstream_model"] == "gpt-4o-mini-2024-07-18"
    assert gateway["cache"]["status"] == "DISABLED"
    assert gateway["fallback"]["used"] is False
    assert gateway["retries"] == 0
    assert gateway["request_id"].startswith("req_")
    assert gateway["latency_ms"] >= 0


async def test_gateway_object_is_not_mixed_into_choices(client: AsyncClient) -> None:
    body = (await client.post("/v1/chat/completions", json=_BODY)).json()
    assert "gateway" not in body["choices"][0]
    assert "gateway" in body


async def test_validation_error_envelope(client: AsyncClient) -> None:
    resp = await client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": []})
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


async def test_streaming_not_implemented_yet(client: AsyncClient) -> None:
    resp = await client.post("/v1/chat/completions", json={**_BODY, "stream": True})
    assert resp.status_code == 501


async def test_unconfigured_provider_is_rejected(client: AsyncClient) -> None:
    resp = await client.post("/v1/chat/completions", json={**_BODY, "provider": "anthropic"})
    assert resp.status_code == 503
    assert resp.json()["error"]["type"] == "provider_not_configured"
