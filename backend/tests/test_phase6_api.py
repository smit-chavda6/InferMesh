"""Phase 6 DoD through the HTTP layer:

* a repeated identical request is served from cache (`cache: HIT`, near-zero
  added latency);
* exceeding the rate limit returns HTTP 429 with a clear body + Retry-After.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Project, RequestLog
from app.security import generate_api_key, hash_api_key, key_display_prefix

from .conftest import http_for, make_app

_BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}


# --- caching ---------------------------------------------------------


async def test_repeated_request_is_served_from_cache(
    db_engine: AsyncEngine, redis_ready, db_session: AsyncSession
) -> None:
    async with make_app(cache_enabled=True) as app, http_for(app) as http:
        first = await http.post("/v1/chat/completions", json=_BODY)
        t0 = time.perf_counter()
        second = await http.post("/v1/chat/completions", json=_BODY)
        hit_wall_ms = (time.perf_counter() - t0) * 1000

    assert first.status_code == second.status_code == 200
    assert first.json()["gateway"]["cache"]["status"] == "MISS"

    g2 = second.json()["gateway"]
    assert g2["cache"]["status"] == "HIT"
    assert g2["cache"]["kind"] == "exact"
    assert g2["cost_usd"] == 0.0
    assert second.json()["choices"][0]["message"]["content"] == "Hello from the OpenAI mock."
    assert hit_wall_ms < 100  # near-zero added latency (Redis GET only)

    rows = list((await db_session.execute(select(RequestLog).order_by(RequestLog.id))).scalars())
    assert len(rows) == 2
    miss, hit = rows
    assert miss.cache_status == "MISS"
    assert hit.cache_status == "HIT"
    assert hit.cost_usd == 0
    assert hit.cache_saved_usd is not None and hit.cache_saved_usd > 0
    assert (hit.prompt_tokens, hit.completion_tokens) == (11, 7)


async def test_cache_is_key_sensitive(db_engine: AsyncEngine, redis_ready) -> None:
    async with make_app(cache_enabled=True) as app, http_for(app) as http:
        await http.post("/v1/chat/completions", json=_BODY)
        other = await http.post(
            "/v1/chat/completions",
            json={**_BODY, "messages": [{"role": "user", "content": "different"}]},
        )
    assert other.json()["gateway"]["cache"]["status"] == "MISS"


# --- rate limiting -------------------------------------------------


async def test_rate_limit_returns_429_with_clear_body(
    db_engine: AsyncEngine, redis_ready, db_session: AsyncSession
) -> None:
    async with (
        make_app(rate_limit_enabled=True, rate_limit_anon_per_minute=3) as app,
        http_for(app) as http,
    ):
        codes = [
            (await http.post("/v1/chat/completions", json=_BODY)).status_code for _ in range(3)
        ]
        blocked = await http.post("/v1/chat/completions", json=_BODY)

    assert codes == [200, 200, 200]
    assert blocked.status_code == 429
    body = blocked.json()["error"]
    assert body["type"] == "rate_limited"
    assert body["limit"] == 3
    assert body["retry_after"] > 0
    assert int(blocked.headers["retry-after"]) >= 1

    row = (
        await db_session.execute(select(RequestLog).where(RequestLog.http_status == 429))
    ).scalar_one()
    assert row.status == "error"
    assert row.error_type == "rate_limited"


async def test_per_project_rate_limit_from_db(
    db_engine: AsyncEngine, redis_ready, db_session: AsyncSession
) -> None:
    key = generate_api_key()
    project = Project(
        name="RAG App",
        key_hash=hash_api_key(key),
        key_prefix=key_display_prefix(key),
        rate_limit_per_minute=2,
        rate_limit_window_seconds=60,
    )
    db_session.add(project)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {key}"}
    async with make_app(rate_limit_enabled=True) as app, http_for(app) as http:
        r1 = await http.post("/v1/chat/completions", json=_BODY, headers=headers)
        r2 = await http.post("/v1/chat/completions", json=_BODY, headers=headers)
        r3 = await http.post("/v1/chat/completions", json=_BODY, headers=headers)

    assert (r1.status_code, r2.status_code, r3.status_code) == (200, 200, 429)
    assert r3.json()["error"]["limit"] == 2

    rows = list((await db_session.execute(select(RequestLog))).scalars())
    assert all(r.project_name == "RAG App" for r in rows)
    assert all(str(r.project_id) == str(project.id) for r in rows)


async def test_invalid_api_key_is_401(db_engine: AsyncEngine, redis_ready) -> None:
    async with make_app() as app, http_for(app) as http:
        resp = await http.post(
            "/v1/chat/completions",
            json=_BODY,
            headers={"Authorization": "Bearer sk-gw-nope"},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "invalid_api_key"


async def test_require_api_key_rejects_anonymous(db_engine: AsyncEngine, redis_ready) -> None:
    async with make_app(require_api_key=True) as app, http_for(app) as http:
        resp = await http.post("/v1/chat/completions", json=_BODY)
    assert resp.status_code == 401


async def test_total_row_count_matches_requests(
    db_engine: AsyncEngine, redis_ready, db_session: AsyncSession
) -> None:
    async with make_app(cache_enabled=True) as app, http_for(app) as http:
        for _ in range(5):
            await http.post("/v1/chat/completions", json=_BODY)
    count = await db_session.scalar(select(func.count()).select_from(RequestLog))
    assert count == 5  # 1 MISS + 4 HITs, still exactly one row each
