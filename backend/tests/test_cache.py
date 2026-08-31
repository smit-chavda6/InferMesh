"""Phase 6: exact-match caching + semantic graceful degradation."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.cache import CachedResponse, ChatCache, Embedder, exact_key
from app.pricing import get_pricing_table
from app.redis_client import RedisClient
from app.schemas.chat import ChatCompletionRequest, ChatMessage

from .conftest import make_settings


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [ChatMessage(role="user", content="ping")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


def _response() -> CachedResponse:
    return CachedResponse(
        id="chatcmpl-x",
        created=1_700_000_000,
        provider="openai",
        model="gpt-4o-mini-2024-07-18",
        role="assistant",
        content="pong",
        finish_reason="stop",
        usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        cost_usd=0.001,
        input_cost_usd=0.0006,
        output_cost_usd=0.0004,
        pricing_version="test",
    )


@pytest.fixture
async def cache(db_engine: AsyncEngine, redis_ready) -> AsyncIterator[ChatCache]:
    settings = make_settings(cache_enabled=True, semantic_cache_enabled=False)
    rc = RedisClient(settings)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    try:
        yield ChatCache(rc.client, maker, Embedder(settings), settings, get_pricing_table())
    finally:
        await rc.close()


def test_exact_key_is_stable_and_param_sensitive() -> None:
    a = exact_key(_req())
    assert a == exact_key(_req())
    assert a != exact_key(_req(temperature=0.5))
    assert a != exact_key(_req(model="gpt-4o"))
    assert a != exact_key(_req(provider="anthropic"))


async def test_miss_then_store_then_hit(cache: ChatCache) -> None:
    req = _req()
    miss = await cache.lookup(req)
    assert miss.hit is False
    assert miss.key is not None

    await cache.store(req, miss.key, _response())

    hit = await cache.lookup(req)
    assert hit.hit is True
    assert hit.kind == "EXACT"
    assert hit.response is not None
    assert hit.response.content == "pong"
    assert hit.response.cost_usd == 0.001


async def test_streaming_requests_are_never_cached(cache: ChatCache) -> None:
    res = await cache.lookup(_req(stream=True))
    assert res.hit is False and res.key is None


async def test_disabled_cache_returns_no_key() -> None:
    settings = make_settings(cache_enabled=False)
    rc = RedisClient(settings)
    try:
        c = ChatCache(rc.client, None, Embedder(settings), settings, get_pricing_table())  # type: ignore[arg-type]
        res = await c.lookup(_req())
        assert res.hit is False and res.key is None
    finally:
        await rc.close()


async def test_semantic_degrades_to_exact_only_without_embedding_key() -> None:
    settings = make_settings(cache_enabled=True, semantic_cache_enabled=True, openai_api_key=None)
    assert settings.semantic_cache_available is False
    embedder = Embedder(settings)
    assert embedder.available is False
    assert await embedder.embed("anything") is None
