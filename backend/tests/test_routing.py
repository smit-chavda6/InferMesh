"""Phase 3: retry + exponential backoff + provider fallback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from app.errors import (
    AllProvidersFailedError,
    GatewayError,
    ProviderBadRequestError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.providers.base import (
    HealthResult,
    NormalizedCompletion,
    NormalizedUsage,
    ProviderAdapter,
    ProviderModel,
    StreamChunk,
)
from app.providers.registry import ProviderRegistry
from app.routing import Router
from app.schemas.chat import ChatCompletionRequest, ChatMessage

from .conftest import make_settings


class ScriptedAdapter(ProviderAdapter):
    """Adapter whose ``complete`` follows a per-call script of outcomes."""

    def __init__(self, name: str, script: list[str | GatewayError]) -> None:
        self.name = name
        self._script = list(script)
        self.calls = 0

    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        self.calls += 1
        step = self._script.pop(0) if self._script else "ok"
        if isinstance(step, GatewayError):
            raise step
        return NormalizedCompletion(
            id=f"{self.name}-resp",
            created=0,
            model=f"{self.name}-model",
            role="assistant",
            content=f"hello from {self.name}",
            finish_reason="stop",
            usage=NormalizedUsage(3, 4, 7),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError
        yield StreamChunk()  # pragma: no cover

    async def list_models(self) -> list[ProviderModel]:
        return []

    async def health_check(self) -> HealthResult:
        return HealthResult(healthy=True)


def build_router(
    adapters: dict[str, ScriptedAdapter], **settings_overrides: object
) -> tuple[Router, AsyncMock]:
    kwargs: dict[str, object] = {
        "retry_base_delay_seconds": 0.0,
        "retry_max_delay_seconds": 0.0,
        "retry_jitter": False,
    }
    kwargs.update(settings_overrides)
    settings = make_settings(**kwargs)
    registry = ProviderRegistry(settings)
    registry._adapters.update(adapters)
    sleep = AsyncMock()
    return Router(registry, settings, sleep=sleep), sleep


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "some-model",
        "messages": [ChatMessage(role="user", content="hi")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


async def test_retries_same_provider_then_succeeds() -> None:
    oa = ScriptedAdapter(
        "openai", [ProviderError("openai", "boom"), ProviderError("openai", "boom"), "ok"]
    )
    router, sleep = build_router({"openai": oa})

    result = await router.execute(_req(provider="openai"))

    assert result.provider_used == "openai"
    assert result.completion.content == "hello from openai"
    assert result.fallback_used is False
    assert result.total_retries == 2
    assert result.attempts[0].outcome == "success"
    assert result.attempts[0].retries == 2
    assert oa.calls == 3
    assert sleep.await_count == 2  # backoff between the 3 attempts


async def test_backoff_delay_grows_exponentially_and_caps() -> None:
    router, _ = build_router(
        {"openai": ScriptedAdapter("openai", ["ok"])},
        retry_base_delay_seconds=0.5,
        retry_max_delay_seconds=8.0,
        retry_backoff_multiplier=2.0,
        retry_jitter=False,
    )
    delays = [router._backoff_delay(i) for i in range(6)]
    assert delays == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]


async def test_falls_back_to_next_provider_after_exhausting_first() -> None:
    oa = ScriptedAdapter("openai", [ProviderTimeoutError("openai", "t")] * 3)
    an = ScriptedAdapter("anthropic", ["ok"])
    router, _ = build_router({"openai": oa, "anthropic": an})

    result = await router.execute(_req())  # no provider -> full chain

    assert result.provider_used == "anthropic"
    assert result.fallback_used is True
    assert [a.provider for a in result.attempts] == ["openai", "anthropic"]
    assert result.attempts[0].outcome == "timeout"
    assert result.attempts[0].retries == 2
    assert result.attempts[1].outcome == "success"
    assert oa.calls == 3 and an.calls == 1


async def test_rate_limit_is_retryable() -> None:
    oa = ScriptedAdapter("openai", [ProviderRateLimitError("openai", "429"), "ok"])
    router, sleep = build_router({"openai": oa})
    result = await router.execute(_req(provider="openai"))
    assert result.provider_used == "openai"
    assert sleep.await_count == 1


async def test_bad_request_is_not_retried_and_does_not_fall_back() -> None:
    oa = ScriptedAdapter("openai", [ProviderBadRequestError("openai", "nope")])
    an = ScriptedAdapter("anthropic", ["ok"])
    router, sleep = build_router({"openai": oa, "anthropic": an})

    with pytest.raises(ProviderBadRequestError):
        await router.execute(_req())

    assert oa.calls == 1
    assert an.calls == 0
    assert sleep.await_count == 0


async def test_all_providers_failing_raises_aggregate_with_attempt_log() -> None:
    adapters = {
        "openai": ScriptedAdapter("openai", [ProviderError("openai", "x")] * 3),
        "anthropic": ScriptedAdapter("anthropic", [ProviderTimeoutError("anthropic", "x")] * 3),
        "gemini": ScriptedAdapter("gemini", [ProviderError("gemini", "x")] * 3),
    }
    router, _ = build_router(adapters)

    with pytest.raises(AllProvidersFailedError) as excinfo:
        await router.execute(_req())

    attempts = excinfo.value.attempts
    assert [a.provider for a in attempts] == ["openai", "anthropic", "gemini"]
    assert all(a.retries == 2 for a in attempts)
    assert {a.outcome for a in attempts} == {"error", "timeout"}


async def test_explicit_provider_still_falls_back_when_enabled() -> None:
    adapters = {
        "anthropic": ScriptedAdapter("anthropic", [ProviderError("anthropic", "x")] * 3),
        "openai": ScriptedAdapter("openai", [ProviderError("openai", "x")] * 3),
        "gemini": ScriptedAdapter("gemini", ["ok"]),
    }
    router, _ = build_router(adapters, fallback_on_explicit_provider=True)

    result = await router.execute(_req(provider="anthropic"))
    assert result.provider_used == "gemini"
    assert [a.provider for a in result.attempts] == ["anthropic", "openai", "gemini"]


async def test_explicit_provider_no_fallback_when_disabled() -> None:
    adapters = {
        "anthropic": ScriptedAdapter("anthropic", [ProviderError("anthropic", "x")] * 3),
        "gemini": ScriptedAdapter("gemini", ["ok"]),
    }
    router, _ = build_router(adapters, fallback_on_explicit_provider=False)

    with pytest.raises(AllProvidersFailedError) as excinfo:
        await router.execute(_req(provider="anthropic"))
    assert [a.provider for a in excinfo.value.attempts] == ["anthropic"]


async def test_hard_timeout_ceiling_wraps_slow_adapter() -> None:
    import asyncio

    class SlowAdapter(ScriptedAdapter):
        async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
            self.calls += 1
            await asyncio.sleep(5)
            raise AssertionError("should have been cancelled")  # pragma: no cover

    slow = SlowAdapter("openai", [])
    ok = ScriptedAdapter("anthropic", ["ok"])
    router, _ = build_router(
        {"openai": slow, "anthropic": ok},
        provider_attempt_timeout_seconds=0.05,
        retry_max_attempts=1,
    )

    result = await router.execute(_req())
    assert result.provider_used == "anthropic"
    assert result.attempts[0].outcome == "timeout"
