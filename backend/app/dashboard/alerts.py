"""Alert evaluation (spec §23).

Rules are simple and explainable — recompute the current alert conditions from
recent request data + dependency pings, then upsert into the ``alerts`` table so
that while a condition holds exactly one ``active`` row exists per
(alert_type, provider), and it flips to ``resolved`` when the condition clears.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.queries import provider_health
from app.db.models import Alert, RequestLog
from app.logging_config import get_logger

log = get_logger(__name__)

_HIGH_ERROR_RATE = 0.10  # 10% of requests errored in the window
_ERROR_RATE_MIN_VOLUME = 20
_RATE_LIMIT_SPIKE = 10  # 429s in the trailing 10 minutes


@dataclass(slots=True)
class Condition:
    alert_type: str
    severity: str
    provider: str | None
    title: str
    message: str
    meta: dict[str, Any]

    @property
    def dedup_key(self) -> tuple[str, str | None]:
        return (self.alert_type, self.provider)


async def _evaluate(session: AsyncSession, *, db_ok: bool, redis_ok: bool) -> list[Condition]:
    conditions: list[Condition] = []

    if not db_ok:
        conditions.append(
            Condition(
                "postgres_unavailable",
                "critical",
                None,
                "PostgreSQL unavailable",
                "The gateway cannot reach its database.",
                {},
            )
        )
    if not redis_ok:
        conditions.append(
            Condition(
                "redis_unavailable",
                "critical",
                None,
                "Redis unavailable",
                "Rate limiting and caching are degraded (fail-open).",
                {},
            )
        )

    for ph in await provider_health(session, window_minutes=5):
        p = ph["provider"]
        if ph["status"] == "unhealthy":
            conditions.append(
                Condition(
                    "provider_unavailable",
                    "critical",
                    p,
                    f"{p} unavailable",
                    f"{p} success rate is {ph['success_rate']:.0%} over the last 5 minutes.",
                    ph,
                )
            )
        elif ph["status"] == "degraded":
            conditions.append(
                Condition(
                    "provider_degraded",
                    "warning",
                    p,
                    f"{p} degraded",
                    (
                        f"{p} success rate is {ph['success_rate']:.0%}"
                        + (
                            " with 3+ consecutive failures"
                            if ph["consecutive_failures_3plus"]
                            else ""
                        )
                        + " over the last 5 minutes."
                    ),
                    ph,
                )
            )
        if ph["request_volume"] >= _ERROR_RATE_MIN_VOLUME and ph["error_rate"] >= _HIGH_ERROR_RATE:
            conditions.append(
                Condition(
                    "high_error_rate",
                    "warning",
                    p,
                    f"High error rate on {p}",
                    f"{p} error rate is {ph['error_rate']:.0%} across "
                    f"{ph['request_volume']} requests.",
                    ph,
                )
            )

    # rate-limit spike: many 429s in the trailing 10 minutes
    since = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    spike = (
        await session.execute(
            select(func.count())
            .select_from(RequestLog)
            .where(RequestLog.http_status == 429, RequestLog.created_at >= since)
        )
    ).scalar_one()
    if int(spike) >= _RATE_LIMIT_SPIKE:
        conditions.append(
            Condition(
                "rate_limit_spike",
                "warning",
                None,
                "Rate-limit spike",
                f"{int(spike)} requests were rate-limited (429) in the last 10 minutes.",
                {"count": int(spike)},
            )
        )
    return conditions


async def evaluate_alerts(
    session: AsyncSession, *, db_ok: bool = True, redis_ok: bool = True
) -> None:
    conditions = await _evaluate(session, db_ok=db_ok, redis_ok=redis_ok)
    active_keys = {c.dedup_key for c in conditions}
    now = dt.datetime.now(dt.UTC)

    existing = {
        (a.alert_type, a.provider): a
        for a in (await session.execute(select(Alert).where(Alert.status == "active"))).scalars()
    }

    for c in conditions:
        row = existing.get(c.dedup_key)
        if row is None:
            session.add(
                Alert(
                    alert_type=c.alert_type,
                    severity=c.severity,
                    status="active",
                    provider=c.provider,
                    title=c.title,
                    message=c.message,
                    meta=c.meta,
                    last_seen_at=now,
                )
            )
        else:
            row.severity = c.severity
            row.title = c.title
            row.message = c.message
            row.meta = c.meta
            row.last_seen_at = now

    for key, row in existing.items():
        if key not in active_keys:
            row.status = "resolved"
            row.resolved_at = now

    await session.commit()
