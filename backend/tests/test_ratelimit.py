"""Phase 6: Redis sliding-window rate limiter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.ratelimit import RateLimiter
from app.redis_client import RedisClient

from .conftest import make_settings


@pytest.fixture
async def limiter(redis_ready) -> AsyncIterator[RateLimiter]:
    rc = RedisClient(make_settings())
    try:
        yield RateLimiter(rc, key_prefix="test_rl", fail_open=True)
    finally:
        await rc.close()


async def test_allows_up_to_limit_then_blocks(limiter: RateLimiter) -> None:
    results = [await limiter.check("client-a", limit=3, window_seconds=60) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert [r.remaining for r in results] == [2, 1, 0, 0]
    assert results[-1].retry_after > 0
    assert results[-1].current == 3


async def test_identifiers_are_independent(limiter: RateLimiter) -> None:
    for _ in range(3):
        assert (await limiter.check("a", 3, 60)).allowed
    assert not (await limiter.check("a", 3, 60)).allowed
    assert (await limiter.check("b", 3, 60)).allowed  # different bucket


async def test_sliding_window_frees_slots_over_time(limiter: RateLimiter) -> None:
    assert (await limiter.check("c", 2, 1)).allowed
    assert (await limiter.check("c", 2, 1)).allowed
    assert not (await limiter.check("c", 2, 1)).allowed
    await asyncio.sleep(1.1)
    assert (await limiter.check("c", 2, 1)).allowed  # oldest entry aged out


async def test_fail_open_when_redis_unavailable() -> None:
    rc = RedisClient(make_settings(redis_url="redis://127.0.0.1:6399/0"))  # nothing there
    try:
        limiter = RateLimiter(rc, fail_open=True)
        res = await limiter.check("x", 1, 60)
        assert res.allowed is True
        assert res.degraded is True
    finally:
        await rc.close()


async def test_fail_closed_when_configured() -> None:
    rc = RedisClient(make_settings(redis_url="redis://127.0.0.1:6399/0"))
    try:
        limiter = RateLimiter(rc, fail_open=False)
        res = await limiter.check("x", 1, 60)
        assert res.allowed is False
        assert res.degraded is True
    finally:
        await rc.close()
