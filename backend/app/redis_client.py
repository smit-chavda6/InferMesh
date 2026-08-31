"""Async Redis connection, owned by the app lifespan.

Redis holds only ephemeral state: rate-limit counters and exact-match cache
entries. Persistent data always lives in Postgres (spec §28).
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.config import Settings
from app.logging_config import get_logger

log = get_logger(__name__)


class RedisClient:
    def __init__(self, settings: Settings) -> None:
        self._client: aioredis.Redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )

    @property
    def client(self) -> aioredis.Redis:
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception as exc:  # noqa: BLE001 - boolean liveness probe; callers act on it
            log.warning("redis.ping_failed", error=str(exc))
            return False

    async def close(self) -> None:
        await self._client.aclose()
