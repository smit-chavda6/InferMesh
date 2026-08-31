"""Anthropic provider adapter.

Translates the gateway's OpenAI-compatible request into the Anthropic Messages
API and normalizes the response back. Like the OpenAI adapter, SDK-level retries
are disabled (``max_retries=0``) — retry/backoff/fallback belong to the gateway.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.config import Settings
from app.errors import (
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.logging_config import get_logger
from app.providers._common import split_system_and_turns, text_of
from app.providers.base import (
    HealthResult,
    NormalizedCompletion,
    NormalizedUsage,
    ProviderAdapter,
    ProviderModel,
    StreamChunk,
)
from app.schemas.chat import ChatCompletionRequest

log = get_logger(__name__)

# Anthropic stop_reason -> OpenAI finish_reason
_FINISH_REASON = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "pause_turn": "stop",
    "refusal": "content_filter",
}


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(self, settings: Settings, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._settings = settings
        if client is not None:
            self._client: anthropic.AsyncAnthropic = client
        elif not settings.anthropic_api_key:
            raise ProviderNotConfiguredError("anthropic", "ANTHROPIC_API_KEY is not set")
        else:
            kwargs: dict[str, Any] = {
                "api_key": settings.anthropic_api_key,
                "timeout": settings.anthropic_timeout_seconds,
                "max_retries": 0,
            }
            if settings.anthropic_base_url:
                kwargs["base_url"] = settings.anthropic_base_url
            self._client = anthropic.AsyncAnthropic(**kwargs)

    # -- helpers ------------------------------------------------------------

    def _resolve_model(self, request_model: str) -> str:
        return request_model or self._settings.anthropic_default_model

    def _build_kwargs(self, request: ChatCompletionRequest) -> dict[str, Any]:
        system, turns = split_system_and_turns(request.messages)
        messages = [
            {
                "role": "assistant" if m.role == "assistant" else "user",
                "content": text_of(m.content),
            }
            for m in turns
        ]
        kwargs: dict[str, Any] = {
            "model": self._resolve_model(request.model),
            "messages": messages,
            # Anthropic requires max_tokens; honor the request, else a config default.
            "max_tokens": request.max_tokens or self._settings.anthropic_default_max_tokens,
        }
        if system:
            kwargs["system"] = system
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.stop is not None:
            kwargs["stop_sequences"] = (
                [request.stop] if isinstance(request.stop, str) else request.stop
            )
        return kwargs

    @staticmethod
    def _map_error(exc: anthropic.AnthropicError) -> ProviderError:
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderTimeoutError("anthropic", str(exc))
        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderAuthError("anthropic", str(exc))
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderRateLimitError("anthropic", str(exc))
        if isinstance(exc, anthropic.BadRequestError):
            return ProviderBadRequestError("anthropic", str(exc))
        if isinstance(exc, anthropic.APIStatusError):
            return ProviderError("anthropic", f"upstream returned {exc.status_code}: {exc}")
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderError("anthropic", f"connection error: {exc}")
        return ProviderError("anthropic", str(exc))

    # -- interface --------------------------------------------------------

    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        kwargs = self._build_kwargs(request)
        try:
            msg = await self._client.messages.create(**kwargs)
        except anthropic.AnthropicError as exc:
            raise self._map_error(exc) from exc
        except Exception as exc:  # provider boundary: always re-raise as a typed error
            log.warning("anthropic.unexpected_error", error=str(exc), error_type=type(exc).__name__)
            raise ProviderError("anthropic", f"{type(exc).__name__}: {exc}") from exc

        text_parts = [
            block.text
            for block in msg.content
            if getattr(block, "type", None) == "text" and hasattr(block, "text")
        ]
        content = "".join(text_parts) if text_parts else None

        return NormalizedCompletion(
            id=msg.id or f"msg_{uuid.uuid4().hex}",
            created=int(time.time()),
            model=msg.model,
            role=msg.role,
            content=content,
            finish_reason=_FINISH_REASON.get(msg.stop_reason or "", msg.stop_reason),
            usage=NormalizedUsage(
                prompt_tokens=msg.usage.input_tokens,
                completion_tokens=msg.usage.output_tokens,
                total_tokens=msg.usage.input_tokens + msg.usage.output_tokens,
            ),
            raw=msg.model_dump(),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError("streaming is implemented in Phase 5")
        yield StreamChunk()  # pragma: no cover

    async def list_models(self) -> list[ProviderModel]:
        try:
            page = await self._client.models.list(limit=100)
        except anthropic.AnthropicError as exc:
            raise self._map_error(exc) from exc
        return [
            ProviderModel(
                id=m.id,
                created=int(m.created_at.timestamp()) if getattr(m, "created_at", None) else None,
                owned_by="anthropic",
            )
            for m in page.data
        ]

    async def health_check(self) -> HealthResult:
        start = time.perf_counter()
        try:
            page = await self._client.models.list(limit=5)
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            log.warning("anthropic.health_check.failed", error=str(exc))
            return HealthResult(healthy=False, detail=str(exc))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return HealthResult(
            healthy=True, latency_ms=latency_ms, checked_models=[m.id for m in page.data[:5]]
        )

    async def aclose(self) -> None:
        await self._client.close()
