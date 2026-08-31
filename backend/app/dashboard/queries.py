"""SQL-side aggregation queries for the dashboard endpoints (spec §29).

All summarisation happens in Postgres (``GROUP BY``, ``FILTER``,
``percentile_cont``, ``date_bin``) — the API returns dashboard-ready shapes, never
raw rows for the browser to reduce.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.timerange import TimeRange

# Columns a client may sort the Requests Explorer by (§13).
REQUEST_SORT_COLUMNS = {
    "created_at",
    "latency_ms",
    "total_tokens",
    "cost_usd",
    "provider",
    "model",
    "status",
}


def _f(v: Decimal | float | None) -> float:
    return float(v) if v is not None else 0.0


async def usage_summary(session: AsyncSession, tr: TimeRange) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
            SELECT
              count(*)                                              AS total,
              count(*) FILTER (WHERE status = 'success')            AS success,
              count(*) FILTER (WHERE status = 'error')              AS errors,
              count(*) FILTER (WHERE fallback_used)                 AS fallback,
              count(*) FILTER (WHERE cache_status = 'HIT')          AS cache_hits,
              count(*) FILTER (WHERE cache_status = 'MISS')         AS cache_misses,
              coalesce(sum(cost_usd), 0)                            AS cost,
              coalesce(sum(cache_saved_usd), 0)                     AS cost_saved,
              coalesce(sum(prompt_tokens), 0)                       AS input_tokens,
              coalesce(sum(completion_tokens), 0)                   AS output_tokens,
              coalesce(avg(latency_ms) FILTER (WHERE status='success'), 0)  AS latency_mean,
              coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms)
                       FILTER (WHERE status='success'), 0)          AS latency_p50,
              coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
                       FILTER (WHERE status='success'), 0)          AS latency_p95
            FROM requests
            WHERE created_at >= :start AND created_at < :end
            """),
            {"start": tr.start, "end": tr.end},
        )
    ).one()

    prev = (
        await session.execute(
            text("""
            SELECT count(*) AS total, coalesce(sum(cost_usd), 0) AS cost
            FROM requests WHERE created_at >= :ps AND created_at < :pe
            """),
            {"ps": tr.prev_start, "pe": tr.prev_end},
        )
    ).one()

    total = int(row.total)
    success = int(row.success)
    cache_hits, cache_misses = int(row.cache_hits), int(row.cache_misses)

    return {
        "range": {"key": tr.key, "start": tr.start, "end": tr.end},
        "total_requests": total,
        "total_requests_prev": int(prev.total),
        "success_count": success,
        "error_count": int(row.errors),
        "success_rate": round(success / total, 4) if total else None,
        "total_cost_usd": _f(row.cost),
        "total_cost_usd_prev": _f(prev.cost),
        "cost_saved_usd": _f(row.cost_saved),
        "fallback_count": int(row.fallback),
        "fallback_rate": round(int(row.fallback) / total, 4) if total else None,
        "cache_hit_count": cache_hits,
        "cache_miss_count": cache_misses,
        "cache_hit_rate": (
            round(cache_hits / (cache_hits + cache_misses), 4)
            if (cache_hits + cache_misses)
            else None
        ),
        "input_tokens": int(row.input_tokens),
        "output_tokens": int(row.output_tokens),
        "latency_ms": {
            "mean": round(_f(row.latency_mean), 2),
            "p50": round(_f(row.latency_p50), 2),
            "p95": round(_f(row.latency_p95), 2),
        },
    }


async def usage_timeseries(session: AsyncSession, tr: TimeRange) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
            SELECT
              date_bin(make_interval(secs => :bucket_secs), created_at, :origin) AS ts,
              count(*)                                          AS total,
              count(*) FILTER (WHERE status = 'success')        AS success,
              count(*) FILTER (WHERE status = 'error')          AS error,
              count(*) FILTER (WHERE fallback_used)             AS fallback,
              coalesce(sum(cost_usd), 0)                        AS cost,
              coalesce(avg(latency_ms) FILTER (WHERE status='success'), 0) AS avg_latency
            FROM requests
            WHERE created_at >= :start AND created_at < :end
            GROUP BY 1 ORDER BY 1
            """),
            {
                "bucket_secs": tr.bucket_seconds,
                "origin": tr.start,
                "start": tr.start,
                "end": tr.end,
            },
        )
    ).all()
    return [
        {
            "ts": r.ts,
            "total": int(r.total),
            "success": int(r.success),
            "error": int(r.error),
            "fallback": int(r.fallback),
            "cost_usd": _f(r.cost),
            "avg_latency_ms": round(_f(r.avg_latency), 2),
        }
        for r in rows
    ]


async def sparkline(session: AsyncSession, tr: TimeRange, points: int = 24) -> list[int]:
    step = max(tr.seconds // points, 60)
    rows = (
        await session.execute(
            text("""
            SELECT date_bin(make_interval(secs => :step), created_at, :origin) AS ts, count(*) AS n
            FROM requests WHERE created_at >= :start AND created_at < :end
            GROUP BY 1 ORDER BY 1
            """),
            {"step": step, "origin": tr.start, "start": tr.start, "end": tr.end},
        )
    ).all()
    return [int(r.n) for r in rows]


async def requests_page(
    session: AsyncSession,
    tr: TimeRange,
    *,
    page: int,
    page_size: int,
    sort: str,
    direction: str,
    provider: str | None = None,
    model: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    fallback_only: bool = False,
    cache_hit_only: bool = False,
    search: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    where = ["created_at >= :start", "created_at < :end"]
    params: dict[str, Any] = {"start": tr.start, "end": tr.end}
    if provider:
        where.append("provider = :provider")
        params["provider"] = provider
    if model:
        where.append("model = :model")
        params["model"] = model
    if status:
        where.append("status = :status")
        params["status"] = status
    if project_id:
        where.append("project_id = cast(:project_id as uuid)")
        params["project_id"] = project_id
    if fallback_only:
        where.append("fallback_used")
    if cache_hit_only:
        where.append("cache_status = 'HIT'")
    if search:
        where.append("(request_id ILIKE :q OR error_type ILIKE :q OR model ILIKE :q)")
        params["q"] = f"%{search}%"
    where_sql = " AND ".join(where)

    total = (
        await session.execute(text(f"SELECT count(*) FROM requests WHERE {where_sql}"), params)
    ).scalar_one()

    sort_col = sort if sort in REQUEST_SORT_COLUMNS else "created_at"
    dir_sql = "DESC" if direction.lower() != "asc" else "ASC"
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    rows = (
        (
            await session.execute(
                text(f"""
            SELECT request_id, created_at, provider, model, upstream_model, status,
                   http_status, error_type, latency_ms, prompt_tokens, completion_tokens,
                   total_tokens, cost_usd, cache_status, fallback_used, retries,
                   project_id, project_name, api_key_prefix, finish_reason, streamed
            FROM requests WHERE {where_sql}
            ORDER BY {sort_col} {dir_sql} NULLS LAST, request_id {dir_sql}
            LIMIT :limit OFFSET :offset
            """),
                params,
            )
        )
        .mappings()
        .all()
    )

    items = [
        {
            **dict(r),
            "created_at": r["created_at"],
            "cost_usd": _f(r["cost_usd"]),
            "project_id": str(r["project_id"]) if r["project_id"] else None,
        }
        for r in rows
    ]
    return items, int(total)


# group_by -> (select cols, group-by cols)
_BREAKDOWN_DIM = {
    "model": ("provider, model", "provider, model"),
    "provider": ("provider", "provider"),
    "project": ("coalesce(project_name, 'anonymous') AS grp", "grp"),
}


async def cost_breakdown(
    session: AsyncSession, tr: TimeRange, group_by: str = "model"
) -> list[dict[str, Any]]:
    sel, grp = _BREAKDOWN_DIM.get(group_by, _BREAKDOWN_DIM["model"])
    rows = (
        (
            await session.execute(
                text(f"""
                SELECT {sel},
                       count(*)                            AS requests,
                       coalesce(sum(prompt_tokens), 0)     AS input_tokens,
                       coalesce(sum(completion_tokens), 0) AS output_tokens,
                       coalesce(sum(cost_usd), 0)          AS cost,
                       coalesce(sum(cache_saved_usd), 0)   AS saved
                FROM requests
                WHERE created_at >= :start AND created_at < :end
                GROUP BY {grp}
                ORDER BY cost DESC
                """),
                {"start": tr.start, "end": tr.end},
            )
        )
        .mappings()
        .all()
    )
    out = []
    for r in rows:
        reqs = int(r["requests"])
        row: dict[str, Any] = {
            "requests": reqs,
            "input_tokens": int(r["input_tokens"]),
            "output_tokens": int(r["output_tokens"]),
            "cost_usd": _f(r["cost"]),
            "cost_saved_usd": _f(r["saved"]),
            "avg_cost_per_request": round(_f(r["cost"]) / reqs, 8) if reqs else 0.0,
        }
        if group_by == "model":
            row["provider"], row["model"] = r["provider"], r["model"]
        elif group_by == "provider":
            row["provider"] = r["provider"]
        else:
            row["project"] = r["grp"]
        out.append(row)
    return out


async def provider_rollup(session: AsyncSession, tr: TimeRange) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
            SELECT provider,
                   count(*)                                     AS requests,
                   count(*) FILTER (WHERE status='error')       AS errors,
                   count(*) FILTER (WHERE fallback_used)        AS fallback,
                   coalesce(sum(cost_usd), 0)                   AS cost,
                   coalesce(avg(latency_ms) FILTER (WHERE status='success'), 0) AS avg_latency,
                   coalesce(sum(total_tokens), 0)               AS tokens
            FROM requests
            WHERE created_at >= :start AND created_at < :end
            GROUP BY provider ORDER BY requests DESC
            """),
            {"start": tr.start, "end": tr.end},
        )
    ).all()
    out = []
    for r in rows:
        reqs = int(r.requests)
        out.append(
            {
                "provider": r.provider,
                "requests": reqs,
                "error_count": int(r.errors),
                "error_rate": round(int(r.errors) / reqs, 4) if reqs else 0.0,
                "fallback_count": int(r.fallback),
                "cost_usd": _f(r.cost),
                "avg_latency_ms": round(_f(r.avg_latency), 2),
                "total_tokens": int(r.tokens),
            }
        )
    return out


async def provider_health(session: AsyncSession, window_minutes: int = 5) -> list[dict[str, Any]]:
    """Trailing-window health per §2.1: Healthy >=99%, Degraded 95-99% or 3+
    consecutive failures, Unhealthy <95%."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=window_minutes)
    rows = (
        await session.execute(
            text("""
            WITH recent AS (
              SELECT provider, status, latency_ms, created_at,
                     row_number() OVER (PARTITION BY provider ORDER BY created_at DESC) AS rn
              FROM requests WHERE created_at >= :since
            )
            SELECT provider,
                   count(*)                                   AS total,
                   count(*) FILTER (WHERE status='success')   AS success,
                   count(*) FILTER (WHERE status='error')     AS errors,
                   coalesce(avg(latency_ms) FILTER (WHERE status='success'), 0) AS avg_latency,
                   bool_and(status='error') FILTER (WHERE rn <= 3) AS last3_all_error,
                   count(*) FILTER (WHERE rn <= 3)            AS last3_count
            FROM recent GROUP BY provider
            """),
            {"since": since},
        )
    ).all()

    out = []
    for r in rows:
        total = int(r.total)
        rate = (int(r.success) / total) if total else 1.0
        consec3 = bool(r.last3_all_error) and int(r.last3_count) >= 3
        if rate < 0.95:
            status = "unhealthy"
        elif rate < 0.99 or consec3:
            status = "degraded"
        else:
            status = "healthy"
        out.append(
            {
                "provider": r.provider,
                "status": status,
                "success_rate": round(rate, 4),
                "error_rate": round(int(r.errors) / total, 4) if total else 0.0,
                "avg_latency_ms": round(_f(r.avg_latency), 2),
                "request_volume": total,
                "consecutive_failures_3plus": consec3,
                "window_minutes": window_minutes,
            }
        )
    return out


async def cost_saved_estimates(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
            SELECT
              count(*) FILTER (WHERE cache_status='HIT')  AS hits,
              count(*) FILTER (WHERE cache_status='MISS') AS misses,
              coalesce(sum(cache_saved_usd)
                       FILTER (WHERE cache_status='HIT'), 0) AS cost_saved,
              coalesce(avg(latency_ms)
                       FILTER (WHERE cache_status='MISS'), 0) AS avg_miss_latency
            FROM requests
            """)
        )
    ).one()
    hits, misses = int(row.hits), int(row.misses)
    return {
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / (hits + misses), 4) if (hits + misses) else None,
        "cost_saved_usd": _f(row.cost_saved),
        "latency_saved_ms_est": round(hits * _f(row.avg_miss_latency), 1),
    }


async def recent_semantic_entries(session: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
            SELECT prompt_hash, model, provider, created_at, expires_at, hits, cost_usd
            FROM semantic_cache ORDER BY created_at DESC LIMIT :limit
            """),
            {"limit": limit},
        )
    ).all()
    return [
        {
            "cache_key": r.prompt_hash,
            "model": r.model,
            "provider": r.provider,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
            "hits": int(r.hits),
            "estimated_savings_usd": _f(r.cost_usd) * int(r.hits),
        }
        for r in rows
    ]


async def projects_with_rollup(session: AsyncSession) -> list[dict[str, Any]]:
    # One aggregate scan of `requests` grouped by project_id, joined to projects —
    # cheaper than a per-project LATERAL when there are many rows.
    rows = (
        await session.execute(
            text("""
            SELECT p.id, p.name, p.key_prefix, p.status, p.rate_limit_per_minute,
                   p.rate_limit_window_seconds, p.created_at, p.last_used_at,
                   coalesce(r.requests, 0) AS requests,
                   coalesce(r.cost, 0)     AS cost,
                   r.last_request_at
            FROM projects p
            LEFT JOIN (
              SELECT project_id,
                     count(*)        AS requests,
                     sum(cost_usd)   AS cost,
                     max(created_at) AS last_request_at
              FROM requests WHERE project_id IS NOT NULL
              GROUP BY project_id
            ) r ON r.project_id = p.id
            ORDER BY p.created_at DESC
            """)
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "key_prefix": r.key_prefix,
            "status": r.status,
            "rate_limit_per_minute": int(r.rate_limit_per_minute),
            "rate_limit_window_seconds": int(r.rate_limit_window_seconds),
            "created_at": r.created_at,
            "last_used_at": r.last_used_at or r.last_request_at,
            "requests": int(r.requests),
            "cost_usd": _f(r.cost),
        }
        for r in rows
    ]


async def recent_429_events(session: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
            SELECT request_id, created_at, project_id, project_name, api_key_prefix
            FROM requests WHERE http_status = 429
            ORDER BY created_at DESC LIMIT :limit
            """),
            {"limit": limit},
        )
    ).all()
    return [
        {
            "request_id": r.request_id,
            "created_at": r.created_at,
            "project_id": str(r.project_id) if r.project_id else None,
            "project_name": r.project_name,
            "api_key_prefix": r.api_key_prefix,
        }
        for r in rows
    ]
