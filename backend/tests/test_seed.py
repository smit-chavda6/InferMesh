"""Phase 9: the seed script produces a sane distribution and real KPI numbers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.dashboard.queries import projects_with_rollup, provider_rollup, usage_summary
from app.dashboard.timerange import resolve_range
from app.db.models import Project, RequestLog
from scripts.seed import seed

from .conftest import make_settings


async def test_seed_produces_realistic_distribution(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    written = await seed(
        rows=3000,
        days=14,
        n_projects=4,
        truncate=True,
        rng_seed=7,
        settings=make_settings(),
        quiet=True,
    )
    assert written == 3000

    total = await db_session.scalar(select(func.count()).select_from(RequestLog))
    assert total == 3000
    assert (await db_session.scalar(select(func.count()).select_from(Project))) == 4

    # provider mix roughly matches the configured weights (openai heaviest)
    by_provider = dict(
        (
            await db_session.execute(
                select(RequestLog.provider, func.count()).group_by(RequestLog.provider)
            )
        ).all()
    )
    assert set(by_provider) == {"openai", "anthropic", "gemini"}
    assert by_provider["openai"] > by_provider["anthropic"] > by_provider["gemini"]

    # a plausible slice of errors / fallback / cache hits / streamed
    errors = await db_session.scalar(select(func.count()).where(RequestLog.status == "error"))
    hits = await db_session.scalar(select(func.count()).where(RequestLog.cache_status == "HIT"))
    assert 0.01 < errors / 3000 < 0.10
    assert 0.10 < hits / 3000 < 0.35

    # cost columns are real (from the pricing table)
    total_cost = await db_session.scalar(select(func.coalesce(func.sum(RequestLog.cost_usd), 0)))
    assert total_cost > 0

    # time spread over the requested window
    span_days = await db_session.scalar(
        select(func.extract("day", func.now() - func.min(RequestLog.created_at)))
    )
    assert 10 <= span_days <= 15


async def test_kpi_endpoints_return_nontrivial_numbers(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    await seed(
        rows=2500,
        days=7,
        n_projects=3,
        truncate=True,
        rng_seed=3,
        settings=make_settings(),
        quiet=True,
    )
    tr = resolve_range("30d")

    summary = await usage_summary(db_session, tr)
    assert summary["total_requests"] == 2500
    assert 0.85 < summary["success_rate"] < 1.0
    assert summary["total_cost_usd"] > 0
    assert summary["cost_saved_usd"] > 0
    assert summary["latency_ms"]["p50"] <= summary["latency_ms"]["p95"]
    assert summary["input_tokens"] > 0 and summary["output_tokens"] > 0

    rollup = await provider_rollup(db_session, tr)
    assert sum(r["requests"] for r in rollup) == 2500

    projects = await projects_with_rollup(db_session)
    assert len(projects) == 3
    assert sum(p["requests"] for p in projects) > 0
