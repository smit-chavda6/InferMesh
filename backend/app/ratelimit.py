"""Redis-backed sliding-window rate limiter.

A per-identifier sorted set of request timestamps (a sliding *log*, not a
fixed-window counter — no boundary burst). The check-and-increment runs in a Lua
script so it is atomic under concurrency.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.logging_config import get_logger
from app.redis_client import RedisClient

log = get_logger(__name__)

_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry_after = 0
  if oldest[2] then
    retry_after = (tonumber(oldest[2]) + window - now) / 1000.0
  end
  return {0, count, limit, tostring(retry_after)}
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)
return {1, count + 1, limit, '0'}
"""


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    current: int
    retry_after: float
    degraded: bool = False  # Redis unavailable -> decision was fail-open/closed

    @property
    def reset_seconds(self) -> float:
        return self.retry_after


class RateLimiter:
    def __init__(
        self, redis: RedisClient, *, key_prefix: str = "ratelimit", fail_open: bool = True
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._fail_open = fail_open
        self._script = redis.client.register_script(_LUA)

    async def check(self, identifier: str, limit: int, window_seconds: int) -> RateLimitResult:
        key = f"{self._prefix}:{identifier}"
        now_ms = time.time() * 1000.0
        window_ms = window_seconds * 1000.0
        try:
            raw = await self._script(keys=[key], args=[now_ms, window_ms, limit, uuid.uuid4().hex])
        except Exception as exc:  # noqa: BLE001 - degrade, decision logged below
            log.warning("ratelimit.redis_error", error=str(exc), fail_open=self._fail_open)
            return RateLimitResult(
                allowed=self._fail_open,
                limit=limit,
                remaining=limit if self._fail_open else 0,
                current=0,
                retry_after=0.0 if self._fail_open else float(window_seconds),
                degraded=True,
            )

        allowed = bool(int(raw[0]))
        current = int(raw[1])
        retry_after = max(float(raw[3]), 0.0)
        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=max(limit - current, 0),
            current=current,
            retry_after=retry_after,
        )
