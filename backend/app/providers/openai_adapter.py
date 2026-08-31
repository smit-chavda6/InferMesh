"""OpenAI / Azure OpenAI provider adapter.

One adapter serves both native OpenAI and Azure OpenAI. ``Settings.openai_mode``
decides which SDK client is constructed; everything downstream (request build,
response normalization, error mapping) is identical.

The gateway disables the SDK's own retry logic (``max_retries=0``) because retry,
backoff and fallback are the gateway's responsibility (Phase 3).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import openai

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


class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self, settings: Settings, client: openai.AsyncOpenAI | None = None) -> None:
        self._settings = settings
        self._mode = settings.openai_mode

        if client is not None:
            self._client: openai.AsyncOpenAI = client
        elif not settings.openai_api_key:
            raise ProviderNotConfiguredError("openai", "OPENAI_API_KEY is not set")
        elif settings.openai_mode == "azure":
            if not settings.azure_openai_endpoint:
                raise ProviderNotConfiguredError("openai", "AZURE_OPENAI_ENDPOINT is not set")
            self._client = openai.AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )
        else:
            kwargs: dict[str, Any] = {
                "api_key": settings.openai_api_key,
                "timeout": settings.openai_timeout_seconds,
                "max_retries": 0,
            }
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = openai.AsyncOpenAI(**kwargs)

    # -- helpers ---------------------------------------------------------------

    def _resolve_model(self, request_model: str) -> str:
        """For Azure the request ``model`` is the deployment name; else fall back to a default."""
        if request_model:
            return request_model
        if self._mode == "azure":
            return self._settings.azure_openai_deployment or ""
        return self._settings.openai_default_model

    def _build_kwargs(self, request: ChatCompletionRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._resolve_model(request.model),
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
        }
        kwargs.update(request.forwarded_params())
        return kwargs

    @staticmethod
    def _map_error(exc: openai.OpenAIError) -> ProviderError:
        if isinstance(exc, openai.APITimeoutError):
            return ProviderTimeoutError("openai", str(exc))
        if isinstance(exc, openai.AuthenticationError):
            return ProviderAuthError("openai", str(exc))
        if isinstance(exc, openai.RateLimitError):
            return ProviderRateLimitError("openai", str(exc))
        if isinstance(exc, openai.BadRequestError):
            return ProviderBadRequestError("openai", str(exc))
        if isinstance(exc, openai.APIStatusError):
            return ProviderError("openai", f"upstream returned {exc.status_code}: {exc}")
        if isinstance(exc, openai.APIConnectionError):
            return ProviderError("openai", f"connection error: {exc}")
        return ProviderError("openai", str(exc))

    # -- interface -----------------------------------------------------------

    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        kwargs = self._build_kwargs(request)
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            raise self._map_error(exc) from exc

        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice is not None else None
        usage = resp.usage

        tool_calls = None
        if message is not None and getattr(message, "tool_calls", None):
            tool_calls = [tc.model_dump() for tc in message.tool_calls]

        return NormalizedCompletion(
            id=resp.id,
            created=resp.created,
            model=resp.model,
            role=(message.role if message is not None else "assistant"),
            content=(message.content if message is not None else None),
            finish_reason=(choice.finish_reason if choice is not None else None),
            usage=NormalizedUsage(
                prompt_tokens=(usage.prompt_tokens if usage else 0),
                completion_tokens=(usage.completion_tokens if usage else 0),
                total_tokens=(usage.total_tokens if usage else 0),
            ),
            tool_calls=tool_calls,
            raw=resp.model_dump(),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError("streaming is implemented in Phase 5")
        yield StreamChunk()  # pragma: no cover  — makes this an async generator

    async def list_models(self) -> list[ProviderModel]:
        try:
            page = await self._client.models.list()
        except openai.OpenAIError as exc:
            raise self._map_error(exc) from exc
        return [
            ProviderModel(
                id=m.id,
                created=getattr(m, "created", None),
                owned_by=getattr(m, "owned_by", None),
            )
            for m in page.data
        ]

    async def health_check(self) -> HealthResult:
        start = time.perf_counter()
        try:
            page = await self._client.models.list()
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            log.warning("openai.health_check.failed", mode=self._mode, error=str(exc))
            return HealthResult(healthy=False, detail=str(exc))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        model_ids = [m.id for m in page.data[:10]]
        return HealthResult(healthy=True, latency_ms=latency_ms, checked_models=model_ids)

    async def aclose(self) -> None:
        await self._client.close()
