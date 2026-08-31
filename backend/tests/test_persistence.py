"""Phase 4 DoD: every gateway request produces exactly one usage row with
correct tokens/cost/latency, and a stored request is queryable by id.
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import RequestLog
from app.errors import ProviderError
from app.main import create_app

from .conftest import make_settings
from .test_routing import ScriptedAdapter

_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


async def _rows(session: AsyncSession) -> list[RequestLog]:
    return list((await session.execute(select(RequestLog).order_by(RequestLog.id))).scalars())


async def test_successful_request_writes_exactly_one_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    resp = await client.post("/v1/chat/completions", json=_BODY)
    assert resp.status_code == 200
    request_id = resp.json()["gateway"]["request_id"]

    count = await db_session.scalar(select(func.count()).select_from(RequestLog))
    assert count == 1

    (row,) = await _rows(db_session)
    assert row.request_id == request_id
    assert row.status == "success"
    assert row.http_status == 200
    assert row.provider == "openai"
    assert row.model == "gpt-4o-mini"
    assert row.upstream_model == "gpt-4o-mini-2024-07-18"
    assert (row.prompt_tokens, row.completion_tokens, row.total_tokens) == (11, 7, 18)
    assert row.latency_ms >= 0
    assert row.fallback_used is False
    assert row.retries == 0
    assert row.cache_status == "DISABLED"
    assert row.message_count == 1
    assert row.finish_reason == "stop"
    assert row.provider_chain and row.provider_chain[0]["provider"] == "openai"


async def test_cost_is_calculated_from_pricing_table(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post("/v1/chat/completions", json=_BODY)
    (row,) = await _rows(db_session)

    assert row.cost_usd is not None and row.cost_usd > 0
    assert row.input_cost_usd is not None and row.output_cost_usd is not None
    assert row.cost_usd == row.input_cost_usd + row.output_cost_usd
    assert row.pricing_version  # stamped with the table version it was costed against


async def test_stored_request_is_queryable_by_id(
    client: AsyncClient, admin_client: AsyncClient
) -> None:
    request_id = (await client.post("/v1/chat/completions", json=_BODY)).json()["gateway"][
        "request_id"
    ]

    # detail endpoint now requires an admin session
    assert (await client.get(f"/v1/requests/{request_id}")).status_code == 401

    got = await admin_client.get(f"/v1/requests/{request_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["request_id"] == request_id
    assert body["provider"] == "openai"
    assert body["total_tokens"] == 18
    assert body["cost_usd"] is not None

    missing = await admin_client.get("/v1/requests/req_does_not_exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["type"] == "request_not_found"


async def test_failed_request_also_writes_one_error_row(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        for name in ("openai", "anthropic", "gemini"):
            app.state.registry._adapters[name] = ScriptedAdapter(
                name, [ProviderError(name, "down")] * 3
            )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
            resp = await http.post("/v1/chat/completions", json=_BODY)

    assert resp.status_code == 502

    rows = await _rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "error"
    assert row.http_status == 502
    assert row.error_type == "all_providers_failed"
    assert row.error_message
    assert row.total_tokens == 0
    assert row.cost_usd is None
    assert [a["provider"] for a in row.provider_chain] == ["openai", "anthropic", "gemini"]


async def test_recording_failure_does_not_break_the_request(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """If the usage write blows up, the client still gets its 200."""
    settings = make_settings()
    app = create_app(settings)
    async with LifespanManager(app):
        app.state.registry._adapters["openai"] = ScriptedAdapter("openai", ["ok"])
        # Sabotage the recorder's DB handle so the usage write raises.
        app.state.recorder._db = None  # type: ignore[assignment]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
            resp = await http.post(
                "/v1/chat/completions",
                json={
                    "provider": "openai",
                    "model": "m",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )

    assert resp.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(RequestLog)) == 0
