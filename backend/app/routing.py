"""Provider router: retry with exponential backoff, then fallback across providers.

``Router.execute`` runs a request through an ordered provider chain. Each provider
gets up to ``retry_max_attempts`` tries with exponential backoff on *retryable*
failures (timeout / rate-limit / upstream 5xx); on a non-retryable failure
(bad request) it stops immediately. If a provider is exhausted, the next provider
in the chain is tried. If every provider fails, ``AllProvidersFailedError`` is
raised carrying the full attempt log.

Retry/backoff/fallback live here, not in adapters and not in the route handler.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.config import Settings
from app.errors import (
    AllProvidersFailedError,
    GatewayError,
    ProviderBadRequestError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.logging_config import get_logger
from app.providers.base import NormalizedCompletion
from app.providers.registry import ProviderRegistry
from app.schemas.chat import ChatCompletionRequest
from app.schemas.gateway import AttemptOutcome, ProviderAttempt

log = get_logger(__name__)

# Outcomes that are worth retrying the *same* provider for.
_RETRYABLE = {"timeout", "rate_limited", "error"}


def _outcome_for(exc: GatewayError) -> AttemptOutcome:
    if isinstance(exc, ProviderTimeoutError):
        return "timeout"
    if isinstance(exc, ProviderRateLimitError):
        return "rate_limited"
    if isinstance(exc, ProviderBadRequestError):
        return "bad_request"
    return "error"


@dataclass(slots=True)
class ExecutionResult:
    completion: NormalizedCompletion
    provider_used: str
    model_used: str
    attempts: list[ProviderAttempt] = field(default_factory=list)

    @property
    def total_retries(self) -> int:
        return sum(a.retries for a in self.attempts)

    @property
    def fallback_used(self) -> bool:
        # More than one provider appears in the attempt log.
        return len({a.provider for a in self.attempts}) > 1


SleepFn = Callable[[float], Awaitable[None]]


class Router:
    def __init__(
        self,
        registry: ProviderRegistry,
        settings: Settings,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._sleep = sleep

    # -- chain construction ------------------------------------------------

    def _provider_chain(self, requested: str | None) -> list[str]:
        s = self._settings
        available = set(s.available_providers())

        if requested is not None:
            if requested not in available:
                raise ProviderNotConfiguredError(requested, "provider is not configured")
            chain = [requested]
            if s.fallback_enabled and s.fallback_on_explicit_provider:
                chain += [p for p in s.fallback_chain if p in available and p != requested]
            return chain

        if not s.fallback_enabled:
            head = s.default_provider
            if head not in available:
                raise ProviderNotConfiguredError(head, "default provider is not configured")
            return [head]

        chain = [p for p in s.fallback_chain if p in available]
        if not chain:
            raise ProviderNotConfiguredError(
                s.default_provider, "no providers in the fallback chain are configured"
            )
        return chain

    def _backoff_delay(self, retry_index: int) -> float:
        """Delay before retry ``retry_index`` (0 = first retry)."""
        s = self._settings
        raw = s.retry_base_delay_seconds * (s.retry_backoff_multiplier**retry_index)
        capped = min(raw, s.retry_max_delay_seconds)
        if s.retry_jitter and capped > 0:
            capped = random.uniform(capped / 2, capped)
        return capped

    # -- execution -------------------------------------------------------

    async def _try_provider(
        self, provider: str, request: ChatCompletionRequest
    ) -> tuple[NormalizedCompletion | None, ProviderAttempt]:
        """Run one provider with its retry loop. Returns (completion|None, attempt log)."""
        adapter = self._registry.get(provider)
        model = request.model or provider
        attempt = ProviderAttempt(provider=provider, model=model, outcome="error")
        max_attempts = self._settings.retry_max_attempts
        started = time.perf_counter()

        last_exc: GatewayError | None = None
        for i in range(max_attempts):
            try:
                completion = await asyncio.wait_for(
                    adapter.complete(request),
                    timeout=self._settings.provider_attempt_timeout_seconds,
                )
                attempt.outcome = "success"
                attempt.retries = i
                attempt.latency_ms = round((time.perf_counter() - started) * 1000, 2)
                return completion, attempt
            except TimeoutError as exc:  # asyncio.wait_for ceiling hit
                last_exc = ProviderTimeoutError(provider, f"attempt exceeded hard timeout: {exc}")
            except ProviderBadRequestError as exc:
                attempt.outcome = "bad_request"
                attempt.retries = i
                attempt.error = str(exc)
                attempt.latency_ms = round((time.perf_counter() - started) * 1000, 2)
                raise
            except GatewayError as exc:
                last_exc = exc

            outcome = _outcome_for(last_exc)
            is_last = i == max_attempts - 1
            log.warning(
                "provider.attempt_failed",
                provider=provider,
                attempt=i + 1,
                max_attempts=max_attempts,
                outcome=outcome,
                will_retry=not is_last and outcome in _RETRYABLE,
                error=str(last_exc),
            )
            if is_last or outcome not in _RETRYABLE:
                break
            await self._sleep(self._backoff_delay(i))

        assert last_exc is not None
        attempt.outcome = _outcome_for(last_exc)
        attempt.retries = max_attempts - 1
        attempt.error = str(last_exc)
        attempt.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return None, attempt

    async def execute(self, request: ChatCompletionRequest) -> ExecutionResult:
        chain = self._provider_chain(request.provider)
        log.info("router.chain", chain=chain, requested=request.provider)

        attempts: list[ProviderAttempt] = []
        for provider in chain:
            completion, attempt = await self._try_provider(provider, request)
            attempts.append(attempt)
            if completion is not None:
                if len(attempts) > 1 or attempt.retries:
                    log.info(
                        "router.recovered",
                        provider_used=provider,
                        providers_tried=[a.provider for a in attempts],
                        total_retries=sum(a.retries for a in attempts),
                    )
                return ExecutionResult(
                    completion=completion,
                    provider_used=provider,
                    model_used=attempt.model,
                    attempts=attempts,
                )
            log.warning("router.provider_exhausted", provider=provider, outcome=attempt.outcome)

        summary = ", ".join(f"{a.provider}:{a.outcome}" for a in attempts)
        raise AllProvidersFailedError(f"all providers failed ({summary})", attempts=list(attempts))
