"""Time-range parsing shared by the dashboard aggregation endpoints.

A range selector value (``1h`` / ``24h`` / ``7d`` / ``30d`` / ``custom``) maps to
a window, the immediately-preceding equal-length window (for % change), and a
server-side bucket width for time-series (per-minute for 1h, per-hour for 24h,
per-day for the longer ranges — never raw per-request points for the long ranges).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

RangeKey = Literal["1h", "24h", "7d", "30d", "custom"]

_SECONDS: dict[str, int] = {"1h": 3600, "24h": 86_400, "7d": 604_800, "30d": 2_592_000}
_BUCKET: dict[str, int] = {  # bucket width in seconds
    "1h": 60,
    "24h": 3600,
    "7d": 86_400,
    "30d": 86_400,
}
_BUCKET_LABEL = {60: "1 minute", 3600: "1 hour", 86_400: "1 day"}


@dataclass(slots=True)
class TimeRange:
    key: str
    start: dt.datetime
    end: dt.datetime
    prev_start: dt.datetime
    prev_end: dt.datetime
    bucket_seconds: int

    @property
    def seconds(self) -> int:
        return int((self.end - self.start).total_seconds())

    @property
    def bucket(self) -> str:
        return _BUCKET_LABEL.get(self.bucket_seconds, f"{self.bucket_seconds} seconds")


def resolve_range(
    key: str = "24h",
    frm: dt.datetime | None = None,
    to: dt.datetime | None = None,
) -> TimeRange:
    now = dt.datetime.now(dt.UTC)

    if key == "custom":
        if frm is None or to is None:
            raise ValueError("custom range requires both 'from' and 'to'")
        start = frm if frm.tzinfo else frm.replace(tzinfo=dt.UTC)
        end = to if to.tzinfo else to.replace(tzinfo=dt.UTC)
        if end <= start:
            raise ValueError("'to' must be after 'from'")
        span = end - start
        bucket_seconds = _bucket_for_span(int(span.total_seconds()))
    elif key in _SECONDS:
        end = now
        start = now - dt.timedelta(seconds=_SECONDS[key])
        span = end - start
        bucket_seconds = _BUCKET[key]
    else:
        raise ValueError(f"unknown range '{key}' (use 1h|24h|7d|30d|custom)")

    return TimeRange(
        key=key,
        start=start,
        end=end,
        prev_start=start - span,
        prev_end=start,
        bucket_seconds=bucket_seconds,
    )


def _bucket_for_span(seconds: int) -> int:
    if seconds <= 3 * 3600:
        return 60
    if seconds <= 3 * 86_400:
        return 3600
    return 86_400


def pct_change(current: float, previous: float) -> float | None:
    """Percentage change vs. the previous period. ``None`` when there is no base."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)
