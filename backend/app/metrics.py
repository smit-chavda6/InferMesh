"""Prometheus metrics for the gateway.

A dedicated ``CollectorRegistry`` (not the process-global default) keeps things
tidy and testable. Every terminal request outcome flows through
``observe_request`` (called from :class:`app.observability.UsageRecorder`); the
circuit breaker updates ``circuit_breaker_state`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client import generate_latest as _generate_latest

if TYPE_CHECKING:
    from app.observability import RequestOutcome

REGISTRY = CollectorRegistry()

requests_total = Counter(
    "gateway_requests_total",
    "Chat-completion requests through the gateway.",
    ["provider", "status", "cache", "fallback", "streamed"],
    registry=REGISTRY,
)
request_latency_seconds = Histogram(
    "gateway_request_latency_seconds",
    "End-to-end gateway latency (seconds).",
    ["provider", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
    registry=REGISTRY,
)
tokens_total = Counter(
    "gateway_tokens_total",
    "Tokens processed, by direction.",
    ["provider", "direction"],  # direction: prompt | completion
    registry=REGISTRY,
)
provider_errors_total = Counter(
    "gateway_provider_errors_total",
    "Errors returned to the caller, by type.",
    ["provider", "error_type"],
    registry=REGISTRY,
)
retries_total = Counter(
    "gateway_retries_total",
    "Retry attempts made against a provider.",
    ["provider"],
    registry=REGISTRY,
)
cache_events_total = Counter(
    "gateway_cache_events_total",
    "Cache lookups, by result.",
    ["result"],  # HIT | MISS | DISABLED
    registry=REGISTRY,
)
circuit_breaker_state = Gauge(
    "gateway_circuit_breaker_state",
    "Per-provider circuit breaker: 0 closed, 1 half-open, 2 open.",
    ["provider"],
    registry=REGISTRY,
)


def observe_request(o: RequestOutcome) -> None:
    """Fold one finished request into the counters/histograms."""
    provider = o.provider or o.requested_provider or "unknown"
    requests_total.labels(
        provider,
        o.status,
        o.cache_status,
        str(o.fallback_used).lower(),
        str(o.streamed).lower(),
    ).inc()
    request_latency_seconds.labels(provider, o.status).observe(max(o.latency_ms, 0.0) / 1000.0)
    if o.prompt_tokens:
        tokens_total.labels(provider, "prompt").inc(o.prompt_tokens)
    if o.completion_tokens:
        tokens_total.labels(provider, "completion").inc(o.completion_tokens)
    if o.status == "error" and o.error_type:
        provider_errors_total.labels(provider, o.error_type).inc()
    if o.retries:
        retries_total.labels(provider).inc(o.retries)
    cache_events_total.labels(o.cache_status or "DISABLED").inc()


_STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def set_circuit_state(provider: str, state: str) -> None:
    circuit_breaker_state.labels(provider).set(_STATE_VALUE.get(state, 0))


def render() -> tuple[bytes, str]:
    """(body, content-type) for the ``/metrics`` exposition endpoint."""
    return _generate_latest(REGISTRY), CONTENT_TYPE_LATEST
