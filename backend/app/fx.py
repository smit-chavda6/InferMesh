"""USD→other-currency rates for the dashboard's display-only currency switch.

Costs are always computed and stored in USD (pricing.yaml). This just fetches a
reference rate (Frankfurter / ECB) once, caches it in Redis for a day, and falls
back to a configured constant if the fetch fails — the number is informational,
not billing.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import redis.asyncio as aioredis

from app.config import Settings
from app.logging_config import get_logger

log = get_logger(__name__)

_CACHE_KEY = "fx:usd:inr"
_CACHE_TTL_SECONDS = 24 * 3600
_ENDPOINT = "https://api.frankfurter.dev/v1/latest"

HttpGet = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]


async def _default_http_get(url: str, params: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=4.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return body


async def usd_inr(
    redis: aioredis.Redis,
    settings: Settings,
    http_get: HttpGet = _default_http_get,
) -> dict[str, Any]:
    """{rate, source, as_of} for 1 USD → INR. Never raises."""
    fallback = {
        "rate": settings.fx_usd_inr_fallback,
        "source": "fallback",
        "as_of": None,
    }
    if not settings.fx_enabled:
        return fallback

    try:
        cached = await redis.get(_CACHE_KEY)
        if cached:
            parsed: dict[str, Any] = json.loads(cached)
            return parsed
    except Exception as exc:  # noqa: BLE001 — cache is best-effort
        log.warning("fx.cache_read_failed", error=str(exc))

    try:
        data = await http_get(_ENDPOINT, {"base": "USD", "symbols": "INR"})
        rate = float(data["rates"]["INR"])
        result = {"rate": round(rate, 4), "source": "frankfurter", "as_of": data.get("date")}
    except Exception as exc:  # noqa: BLE001 — any failure → the configured constant
        log.warning("fx.fetch_failed", error=str(exc))
        return fallback

    try:
        await redis.set(_CACHE_KEY, json.dumps(result), ex=_CACHE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("fx.cache_write_failed", error=str(exc))

    return result
