"""Phase 8 DoD: every §27 read endpoint returns real aggregated data and is
behind admin auth; unauthenticated requests are rejected.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import seed_requests

_PROTECTED = [
    "/v1/usage/summary",
    "/v1/usage/cost-breakdown",
    "/v1/usage/timeseries",
    "/v1/requests",
    "/v1/providers",
    "/v1/providers/health",
    "/v1/cache/stats",
    "/v1/rate-limits",
    "/v1/projects",
    "/v1/alerts",
    "/v1/system/health",
]


@pytest.mark.parametrize("path", _PROTECTED)
async def test_endpoint_requires_admin(client: AsyncClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "admin_auth_required"


async def test_usage_summary_shape(admin_client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_requests(db_session, n=60)
    body = (await admin_client.get("/v1/usage/summary?range=7d")).json()

    assert body["total_requests"] == 60
    assert body["success_count"] + body["error_count"] == 60
    assert 0 < body["success_rate"] <= 1
    assert body["total_cost_usd"] > 0
    assert body["cost_saved_usd"] > 0
    assert body["input_tokens"] > 0 and body["output_tokens"] > 0
    assert body["cache_hit_count"] > 0
    lat = body["latency_ms"]
    assert lat["p50"] <= lat["p95"]
    assert isinstance(body["sparkline"], list) and sum(body["sparkline"]) > 0
    # change-vs-prev keys present (may be None if no prior period)
    assert "total_requests_change_pct" in body


@pytest.mark.parametrize(
    ("group_by", "key"),
    [("model", "model"), ("provider", "provider"), ("project", "project")],
)
async def test_cost_breakdown_shape(
    admin_client: AsyncClient, db_session: AsyncSession, group_by: str, key: str
) -> None:
    await seed_requests(db_session, n=80)
    body = (await admin_client.get(f"/v1/usage/cost-breakdown?range=7d&group_by={group_by}")).json()

    assert body["group_by"] == group_by
    rows = body["rows"]
    assert len(rows) > 0
    # rows are ordered by cost, descending
    costs = [r["cost_usd"] for r in rows]
    assert costs == sorted(costs, reverse=True)
    # every row carries the grouping dimension and consistent aggregates
    assert all(key in r for r in rows)
    if group_by == "model":
        assert all("provider" in r for r in rows)
    for r in rows:
        assert r["requests"] > 0
        assert r["cost_usd"] >= 0
        assert r["input_tokens"] >= 0 and r["output_tokens"] >= 0
        if r["cost_usd"] > 0:
            assert r["avg_cost_per_request"] == pytest.approx(
                r["cost_usd"] / r["requests"], rel=1e-3
            )
    # request counts sum back to the seeded total
    assert sum(r["requests"] for r in rows) == 80


async def test_cost_breakdown_rejects_bad_group_by(admin_client: AsyncClient) -> None:
    resp = await admin_client.get("/v1/usage/cost-breakdown?range=7d&group_by=bogus")
    assert resp.status_code == 422


async def test_usage_timeseries_buckets(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_requests(db_session, n=40)
    body = (await admin_client.get("/v1/usage/timeseries?range=24h")).json()
    assert body["range"]["bucket"] == "1 hour"
    series = body["series"]
    assert len(series) >= 1
    assert all({"ts", "total", "success", "error", "fallback"} <= set(pt) for pt in series)
    assert sum(pt["total"] for pt in series) == 40


async def test_requests_explorer_pagination_and_filter(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_requests(db_session, n=60)

    p1 = (await admin_client.get("/v1/requests?range=7d&page=1&page_size=25")).json()
    assert p1["total"] == 60
    assert len(p1["items"]) == 25
    assert p1["has_more"] is True

    # page_size cap enforced server-side
    capped = (await admin_client.get("/v1/requests?range=7d&page_size=9999")).json()
    assert capped["page_size"] == 200

    # filter: errors only
    errs = (await admin_client.get("/v1/requests?range=7d&status=error&page_size=200")).json()
    assert errs["total"] > 0
    assert all(it["status"] == "error" for it in errs["items"])

    # filter: provider
    oai = (await admin_client.get("/v1/requests?range=7d&provider=openai&page_size=200")).json()
    assert all(it["provider"] == "openai" for it in oai["items"])

    # sort
    asc = (
        await admin_client.get("/v1/requests?range=7d&sort=latency_ms&direction=asc&page_size=200")
    ).json()
    lats = [it["latency_ms"] for it in asc["items"]]
    assert lats == sorted(lats)


async def test_providers_and_health(admin_client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_requests(db_session, n=60)

    providers = (await admin_client.get("/v1/providers?range=7d")).json()
    # every canonical provider is listed, enabled or not (azure_foundry is Phase 11)
    assert {p["provider"] for p in providers["providers"]} == {
        "openai",
        "anthropic",
        "gemini",
        "azure_foundry",
    }
    foundry = next(p for p in providers["providers"] if p["provider"] == "azure_foundry")
    assert foundry["enabled"] is False  # no key configured in tests
    assert providers["routing"]["primary"] == "openai"
    assert any(p["requests"] > 0 for p in providers["providers"])

    health = (await admin_client.get("/v1/providers/health")).json()
    # seeded rows are older than 5 min for most; at least the endpoint returns the shape
    assert "providers" in health


async def test_cache_stats(admin_client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_requests(db_session, n=60)
    body = (await admin_client.get("/v1/cache/stats")).json()
    assert body["hits"] > 0 and body["misses"] > 0
    assert 0 < body["hit_rate"] <= 1
    assert body["cost_saved_usd"] > 0
    assert body["latency_saved_ms_est"] >= 0
    assert isinstance(body["recent_entries"], list)


async def test_rate_limits_lists_projects(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.db.models import Project
    from app.security import generate_api_key, hash_api_key, key_display_prefix

    k = generate_api_key()
    db_session.add(
        Project(
            name="P1",
            key_hash=hash_api_key(k),
            key_prefix=key_display_prefix(k),
            rate_limit_per_minute=50,
        )
    )
    await db_session.commit()

    body = (await admin_client.get("/v1/rate-limits")).json()
    assert body["anon_limit_per_minute"] > 0
    assert any(row["project"] == "P1" and row["limit"] == 50 for row in body["projects"])
    assert "recent_429" in body


async def test_alerts_endpoint(admin_client: AsyncClient, db_session: AsyncSession) -> None:
    body = (await admin_client.get("/v1/alerts")).json()
    assert "alerts" in body and "unread_count" in body
    assert isinstance(body["alerts"], list)


async def test_system_health(admin_client: AsyncClient) -> None:
    body = (await admin_client.get("/v1/system/health")).json()
    assert body["gateway"]["status"] in {"healthy", "degraded"}
    deps = body["dependencies"]
    assert deps["postgres"]["status"] == "healthy"
    assert deps["redis"]["status"] == "healthy"
    assert "openai" in deps


async def test_bad_range_is_400(admin_client: AsyncClient) -> None:
    resp = await admin_client.get("/v1/usage/summary?range=custom")  # missing from/to
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "bad_range"
