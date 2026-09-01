"""GET /metrics — Prometheus exposition, optionally token-gated."""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import http_for, make_app

_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


async def test_metrics_endpoint_exposes_gateway_series(client: AsyncClient) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    for name in (
        "gateway_requests_total",
        "gateway_request_latency_seconds",
        "gateway_tokens_total",
        "gateway_cache_events_total",
        "gateway_circuit_breaker_state",
    ):
        assert name in body


async def test_a_request_increments_the_counter(client: AsyncClient) -> None:
    before = _counter_sum(await _metrics_text(client), "gateway_requests_total")
    await client.post("/v1/chat/completions", json=_BODY)
    after = _counter_sum(await _metrics_text(client), "gateway_requests_total")
    assert after >= before + 1


async def test_version_endpoint(client: AsyncClient) -> None:
    body = (await client.get("/v1/version")).json()
    assert body["version"]
    assert "git_sha" in body and "started_at" in body


async def test_metrics_token_gate(db_engine, redis_ready) -> None:
    async with make_app(metrics_token="s3cret") as app, http_for(app) as http:
        assert (await http.get("/metrics")).status_code == 401
        ok = await http.get("/metrics", headers={"authorization": "Bearer s3cret"})
        assert ok.status_code == 200


async def test_metrics_can_be_disabled(db_engine, redis_ready) -> None:
    async with make_app(metrics_enabled=False) as app, http_for(app) as http:
        assert (await http.get("/metrics")).status_code == 404


# -- helpers -----------------------------------------------------------------


async def _metrics_text(client: AsyncClient) -> str:
    return (await client.get("/metrics")).text


def _counter_sum(text: str, metric: str) -> float:
    total = 0.0
    for line in text.splitlines():
        if line.startswith(metric + "{") or line.startswith(metric + " "):
            total += float(line.rsplit(" ", 1)[-1])
    return total
