"""Admin dashboard read endpoints (spec §27). All require an admin session."""

from __future__ import annotations

import datetime as dt
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.dashboard import queries as q
from app.dashboard.alerts import evaluate_alerts
from app.dashboard.timerange import TimeRange, pct_change, resolve_range
from app.db.models import Alert
from app.db.session import get_session
from app.errors import GatewayError
from app.logging_config import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["dashboard"], dependencies=[Depends(require_admin)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RangeQ = Annotated[str, Query(pattern="^(1h|24h|7d|30d|custom)$")]


class BadRangeError(GatewayError):
    error_type = "bad_range"
    status_code = 400


def _range(key: str, frm: dt.datetime | None, to: dt.datetime | None) -> TimeRange:
    try:
        return resolve_range(key, frm, to)
    except ValueError as exc:
        raise BadRangeError(str(exc)) from exc


# --- usage ---------------------------------------------------------------


@router.get("/usage/summary")
async def usage_summary(
    session: SessionDep,
    range: RangeQ = "24h",
    frm: Annotated[dt.datetime | None, Query(alias="from")] = None,
    to: dt.datetime | None = None,
) -> dict[str, Any]:
    tr = _range(range, frm, to)
    summary = await q.usage_summary(session, tr)
    summary["total_requests_change_pct"] = pct_change(
        summary["total_requests"], summary["total_requests_prev"]
    )
    summary["total_cost_change_pct"] = pct_change(
        summary["total_cost_usd"], summary["total_cost_usd_prev"]
    )
    summary["sparkline"] = await q.sparkline(session, tr)
    return summary


@router.get("/usage/cost-breakdown")
async def cost_breakdown(
    session: SessionDep,
    range: RangeQ = "24h",
    group_by: Annotated[str, Query(pattern="^(model|provider|project)$")] = "model",
    frm: Annotated[dt.datetime | None, Query(alias="from")] = None,
    to: dt.datetime | None = None,
) -> dict[str, Any]:
    tr = _range(range, frm, to)
    return {
        "range": {"key": tr.key, "start": tr.start, "end": tr.end},
        "group_by": group_by,
        "rows": await q.cost_breakdown(session, tr, group_by),
    }


@router.get("/usage/timeseries")
async def usage_timeseries(
    session: SessionDep,
    range: RangeQ = "24h",
    frm: Annotated[dt.datetime | None, Query(alias="from")] = None,
    to: dt.datetime | None = None,
) -> dict[str, Any]:
    tr = _range(range, frm, to)
    return {
        "range": {"key": tr.key, "start": tr.start, "end": tr.end, "bucket": tr.bucket},
        "series": await q.usage_timeseries(session, tr),
    }


# --- providers ---------------------------------------------------------


@router.get("/providers")
async def providers(
    request: Request,
    session: SessionDep,
    range: RangeQ = "24h",
) -> dict[str, Any]:
    settings = request.app.state.settings
    tr = _range(range, None, None)
    rollup = {r["provider"]: r for r in await q.provider_rollup(session, tr)}
    chain = settings.fallback_chain

    items = []
    for name in ("openai", "anthropic", "gemini"):
        stats = rollup.get(name, {})
        items.append(
            {
                "provider": name,
                "enabled": settings.provider_enabled(name),
                "is_primary": name == settings.default_provider,
                "fallback_priority": chain.index(name) + 1 if name in chain else None,
                "requests": stats.get("requests", 0),
                "error_rate": stats.get("error_rate", 0.0),
                "fallback_count": stats.get("fallback_count", 0),
                "avg_latency_ms": stats.get("avg_latency_ms", 0.0),
                "cost_usd": stats.get("cost_usd", 0.0),
                "total_tokens": stats.get("total_tokens", 0),
            }
        )
    return {
        "range": {"key": tr.key, "start": tr.start, "end": tr.end},
        "routing": {
            "primary": settings.default_provider,
            "fallback_chain": chain,
            "fallback_enabled": settings.fallback_enabled,
            "retry_max_attempts": settings.retry_max_attempts,
            "retry_base_delay_seconds": settings.retry_base_delay_seconds,
            "provider_attempt_timeout_seconds": settings.provider_attempt_timeout_seconds,
        },
        "providers": items,
    }


@router.get("/providers/health")
async def providers_health(session: SessionDep) -> dict[str, Any]:
    return {"providers": await q.provider_health(session, window_minutes=5)}


# --- cache -----------------------------------------------------------


@router.get("/cache/stats")
async def cache_stats(request: Request, session: SessionDep) -> dict[str, Any]:
    est = await q.cost_saved_estimates(session)
    redis_stats = await request.app.state.cache.stats()
    return {
        **est,
        "exact_entries": redis_stats.get("exact_entries"),
        "semantic_entries": redis_stats.get("semantic_entries", 0),
        "semantic_enabled": redis_stats.get("semantic_enabled", False),
        "recent_entries": await q.recent_semantic_entries(session),
    }


# --- rate limits ---------------------------------------------------


@router.get("/rate-limits")
async def rate_limits(request: Request, session: SessionDep) -> dict[str, Any]:
    projects = await q.projects_with_rollup(session)
    redis = request.app.state.redis.client
    rows = []
    for p in projects:
        current = 0
        try:
            current = int(await redis.zcard(f"ratelimit:key:{p['id']}"))
        except Exception:  # noqa: BLE001 - best effort
            current = 0
        limit = p["rate_limit_per_minute"]
        rows.append(
            {
                "project_id": p["id"],
                "project": p["name"],
                "status": p["status"],
                "limit": limit,
                "window_seconds": p["rate_limit_window_seconds"],
                "current": current,
                "remaining": max(limit - current, 0),
            }
        )
    return {
        "anon_limit_per_minute": request.app.state.settings.rate_limit_anon_per_minute,
        "projects": rows,
        "recent_429": await q.recent_429_events(session),
    }


# --- projects (read) --------------------------------------------


@router.get("/projects")
async def list_projects(session: SessionDep) -> dict[str, Any]:
    return {"projects": await q.projects_with_rollup(session)}


# --- alerts --------------------------------------------------------


@router.get("/alerts")
async def alerts(request: Request, session: SessionDep) -> dict[str, Any]:
    db_ok = await request.app.state.db.ping()
    redis_ok = await request.app.state.redis.ping()
    try:
        await evaluate_alerts(session, db_ok=db_ok, redis_ok=redis_ok)
    except Exception as exc:  # noqa: BLE001 - never let evaluation break the read
        log.warning("alerts.evaluation_failed", error=str(exc))

    active = (
        (
            await session.execute(
                select(Alert).where(Alert.status == "active").order_by(Alert.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "unread_count": sum(1 for a in active if not a.acknowledged),
        "alerts": [
            {
                "id": a.id,
                "type": a.alert_type,
                "severity": a.severity,
                "status": a.status,
                "provider": a.provider,
                "title": a.title,
                "message": a.message,
                "acknowledged": a.acknowledged,
                "first_seen_at": a.first_seen_at,
                "last_seen_at": a.last_seen_at,
            }
            for a in active
        ],
    }


# --- system health ---------------------------------------------


@router.get("/system/health")
async def system_health(request: Request, session: SessionDep) -> dict[str, Any]:
    app = request.app
    deps: dict[str, Any] = {}
    for name, coro in (("postgres", app.state.db.ping()), ("redis", app.state.redis.ping())):
        t0 = time.perf_counter()
        ok = await coro
        deps[name] = {
            "status": "healthy" if ok else "unhealthy",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "checked_at": dt.datetime.now(dt.UTC),
        }

    ph = {p["provider"]: p for p in await q.provider_health(session, window_minutes=5)}
    for name in ("openai", "anthropic", "gemini"):
        if not app.state.settings.provider_enabled(name):
            deps[name] = {"status": "disabled", "checked_at": dt.datetime.now(dt.UTC)}
        else:
            h = ph.get(name)
            deps[name] = {
                "status": h["status"] if h else "unknown",
                "success_rate": h["success_rate"] if h else None,
                "avg_latency_ms": h["avg_latency_ms"] if h else None,
                "checked_at": dt.datetime.now(dt.UTC),
            }

    gateway_ok = deps["postgres"]["status"] == "healthy" and deps["redis"]["status"] == "healthy"
    return {
        "gateway": {"status": "healthy" if gateway_ok else "degraded"},
        "dependencies": deps,
    }
