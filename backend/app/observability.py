"""Usage recording: exactly one ``requests`` row per gateway request.

Recording is best-effort — a database failure is logged with context but never
turns a successful (or already-failed) API call into a 500. Cost is computed
here from the versioned pricing table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models import RequestLog
from app.db.session import Database
from app.logging_config import get_logger
from app.pricing import PricingTable

log = get_logger(__name__)


@dataclass(slots=True)
class RequestOutcome:
    """Everything needed to write one usage row, filled in by the chat route."""

    request_id: str
    model: str
    message_count: int
    requested_provider: str | None = None

    status: str = "error"  # "success" | "error"
    http_status: int = 500
    latency_ms: float = 0.0
    streamed: bool = False

    # provider actually used + usage (success path)
    provider: str | None = None
    upstream_model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str | None = None

    # reliability
    fallback_used: bool = False
    retries: int = 0
    provider_chain: list[dict[str, Any]] | None = None

    # cache (Phase 6)
    cache_status: str = "DISABLED"
    cache_key: str | None = None

    # error path
    error_type: str | None = None
    error_message: str | None = None

    # populated at record time
    api_key_prefix: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class UsageRecorder:
    def __init__(self, db: Database, pricing: PricingTable, *, enabled: bool = True) -> None:
        self._db = db
        self._pricing = pricing
        self._enabled = enabled

    async def record(self, outcome: RequestOutcome) -> None:
        if not self._enabled:
            return
        try:
            await self._write(outcome)
        except Exception as exc:  # best-effort: log, never propagate
            log.error(
                "usage.record_failed",
                request_id=outcome.request_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    async def _write(self, o: RequestOutcome) -> None:
        cost_provider = o.provider or o.requested_provider
        breakdown = None
        if cost_provider and o.status == "success" and o.total_tokens:
            breakdown = self._pricing.cost(
                cost_provider, o.model, o.prompt_tokens, o.completion_tokens
            )

        row = RequestLog(
            request_id=o.request_id,
            provider=o.provider or o.requested_provider or "unknown",
            model=o.model,
            upstream_model=o.upstream_model,
            status=o.status,
            http_status=o.http_status,
            error_type=o.error_type,
            error_message=(o.error_message or "")[:2000] or None,
            finish_reason=o.finish_reason,
            latency_ms=o.latency_ms,
            prompt_tokens=o.prompt_tokens,
            completion_tokens=o.completion_tokens,
            total_tokens=o.total_tokens,
            cost_usd=breakdown.total_cost_usd if breakdown else None,
            input_cost_usd=breakdown.input_cost_usd if breakdown else None,
            output_cost_usd=breakdown.output_cost_usd if breakdown else None,
            pricing_version=breakdown.pricing_version if breakdown else None,
            fallback_used=o.fallback_used,
            retries=o.retries,
            provider_chain=o.provider_chain,
            cache_status=o.cache_status,
            cache_key=o.cache_key,
            streamed=o.streamed,
            message_count=o.message_count,
            api_key_prefix=o.api_key_prefix,
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
        log.info(
            "usage.recorded",
            request_id=o.request_id,
            provider=row.provider,
            model=row.model,
            status=row.status,
            total_tokens=row.total_tokens,
            cost_usd=(str(row.cost_usd) if row.cost_usd is not None else None),
            latency_ms=row.latency_ms,
        )
