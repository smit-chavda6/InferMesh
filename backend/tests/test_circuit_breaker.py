"""Per-provider circuit breaker: unit behaviour + routing integration."""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.circuit_breaker import CircuitBreaker
from app.errors import ProviderError
from app.main import create_app

from .conftest import make_settings
from .test_routing import ScriptedAdapter

_BODY = {"model": "some-model", "messages": [{"role": "user", "content": "hi"}]}


# --- unit -----------------------------------------------------------------


def test_opens_after_threshold_consecutive_failures() -> None:
    now = [0.0]
    cb = CircuitBreaker(failure_threshold=3, reset_seconds=10, clock=lambda: now[0])

    assert cb.allow("openai") is True
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.state_of("openai") == "closed"
    cb.record_failure("openai")  # third strike
    assert cb.state_of("openai") == "open"
    assert cb.allow("openai") is False


def test_success_resets_the_failure_run() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("x")
    cb.record_failure("x")
    cb.record_success("x")
    cb.record_failure("x")
    cb.record_failure("x")
    assert cb.state_of("x") == "closed"


def test_cooldown_half_opens_then_success_closes() -> None:
    now = [0.0]
    cb = CircuitBreaker(failure_threshold=1, reset_seconds=5, clock=lambda: now[0])

    cb.record_failure("x")
    assert cb.state_of("x") == "open"
    assert cb.allow("x") is False

    now[0] = 6.0
    assert cb.allow("x") is True  # one probe
    assert cb.state_of("x") == "half_open"
    cb.record_success("x")
    assert cb.state_of("x") == "closed"


def test_failed_probe_reopens_the_circuit() -> None:
    now = [0.0]
    cb = CircuitBreaker(failure_threshold=1, reset_seconds=5, clock=lambda: now[0])
    cb.record_failure("x")
    now[0] = 6.0
    cb.allow("x")  # -> half_open
    cb.record_failure("x")
    assert cb.state_of("x") == "open"
    assert cb.allow("x") is False  # cooldown restarted at t=6


def test_snapshot_reports_state_and_retry_countdown() -> None:
    cb = CircuitBreaker(failure_threshold=1, reset_seconds=30)
    cb.record_failure("openai")
    snap = cb.snapshot()["openai"]
    assert snap["state"] == "open"
    assert 0 < snap["retry_in_seconds"] <= 30


# --- routing integration ------------------------------------------------


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")


async def test_open_circuit_is_skipped_by_the_router(db_engine) -> None:
    settings = make_settings(
        retry_base_delay_seconds=0.0,
        retry_jitter=False,
        circuit_breaker_failure_threshold=1,
        circuit_breaker_reset_seconds=999,  # stay open for the whole test
    )
    app = create_app(settings)
    async with LifespanManager(app):
        openai_ad = ScriptedAdapter("openai", [ProviderError("openai", "down")] * 20)
        app.state.registry._adapters.update(
            {"openai": openai_ad, "anthropic": ScriptedAdapter("anthropic", ["ok"] * 5)}
        )
        async with await _client(app) as http:
            r1 = (await http.post("/v1/chat/completions", json=_BODY)).json()
            assert r1["gateway"]["provider"] == "anthropic"  # openai failed -> fell back
            calls_after_first = openai_ad.calls
            assert calls_after_first >= 1

            r2 = (await http.post("/v1/chat/completions", json=_BODY)).json()
            assert r2["gateway"]["provider"] == "anthropic"
            assert openai_ad.calls == calls_after_first  # openai NOT called — circuit open
            chain = r2["gateway"]["fallback"]["chain"]
            assert chain[0]["provider"] == "openai"
            assert chain[0]["outcome"] == "circuit_open"

        # dashboard surfaces the open circuit
        assert app.state.circuit_breaker.state_of("openai") == "open"


async def test_disabled_breaker_keeps_hammering_the_provider(db_engine) -> None:
    settings = make_settings(
        retry_base_delay_seconds=0.0,
        retry_jitter=False,
        circuit_breaker_enabled=False,
        circuit_breaker_failure_threshold=1,
    )
    app = create_app(settings)
    async with LifespanManager(app):
        openai_ad = ScriptedAdapter("openai", [ProviderError("openai", "down")] * 20)
        app.state.registry._adapters.update(
            {"openai": openai_ad, "anthropic": ScriptedAdapter("anthropic", ["ok"] * 5)}
        )
        async with await _client(app) as http:
            await http.post("/v1/chat/completions", json=_BODY)
            first = openai_ad.calls
            await http.post("/v1/chat/completions", json=_BODY)
            assert openai_ad.calls > first  # retried again — no breaker
