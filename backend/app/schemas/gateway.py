"""Gateway metadata attached to every ``/v1/chat/completions`` response.

This object lives alongside the OpenAI-compatible body (never inside ``choices``)
and carries everything the dashboard and clients need to reason about how the
request was actually served.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CacheStatus = Literal["HIT", "MISS", "DISABLED"]
AttemptOutcome = Literal["success", "timeout", "error", "rate_limited", "bad_request"]


class CacheInfo(BaseModel):
    status: CacheStatus = "DISABLED"
    key: str | None = None


class ProviderAttempt(BaseModel):
    """One provider invocation within a (possibly multi-step) fallback chain."""

    provider: str
    model: str
    outcome: AttemptOutcome
    retries: int = 0
    latency_ms: float | None = None
    error: str | None = None


class FallbackInfo(BaseModel):
    used: bool = False
    chain: list[ProviderAttempt] = Field(default_factory=list)


class GatewayMetadata(BaseModel):
    request_id: str
    provider: str
    model: str
    upstream_model: str | None = None
    cache: CacheInfo = Field(default_factory=CacheInfo)
    fallback: FallbackInfo = Field(default_factory=FallbackInfo)
    retries: int = 0
    latency_ms: float
    cost_usd: float | None = None  # populated once pricing lands in Phase 4
