from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "LLM Gateway"
    assert body["providers_available"] == ["openai", "anthropic", "gemini"]
    assert "x-request-id" in resp.headers


async def test_request_id_is_generated(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers["x-request-id"].startswith("req_")


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "req_supplied_by_caller"})
    assert resp.headers["x-request-id"] == "req_supplied_by_caller"
