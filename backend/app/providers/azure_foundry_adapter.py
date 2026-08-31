"""Azure AI Foundry provider adapter (Phase 11).

Talks to the **Azure AI Model Inference API** — the single OpenAI-shaped REST
surface a Foundry resource exposes at
``https://<resource>.services.ai.azure.com/models`` in front of every model
deployed to it. This is deliberately *not* the same as ``OPENAI_MODE=azure``
(Azure OpenAI): different URL path, different api-version line, its own
deployments. Kept dependency-free — a plain ``httpx.AsyncClient`` against the
documented REST contract — because the request/response bodies are already the
gateway's canonical shape.

The gateway owns retry/backoff/fallback, so this adapter makes exactly one
attempt per call and maps every failure to a typed ``ProviderError``.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

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

_NAME = "azure_foundry"


def _inference_base(endpoint: str) -> str:
    """Normalise a configured endpoint to ``<origin>/models`` (idempotent)."""
    base = endpoint.strip().rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


class AzureFoundryAdapter(ProviderAdapter):
    name = _NAME

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._api_version = settings.azure_foundry_api_version
        self._default_model = settings.azure_foundry_model

        if client is not None:
            self._client = client
            self._owns_client = False
            return

        if not settings.azure_foundry_api_key:
            raise ProviderNotConfiguredError(_NAME, "AZURE_FOUNDRY_API_KEY is not set")
        if not settings.azure_foundry_endpoint:
            raise ProviderNotConfiguredError(_NAME, "AZURE_FOUNDRY_ENDPOINT is not set")

        self._client = httpx.AsyncClient(
            base_url=_inference_base(settings.azure_foundry_endpoint),
            headers={
                "api-key": settings.azure_foundry_api_key,
                "content-type": "application/json",
            },
            timeout=settings.azure_foundry_timeout_seconds,
        )
        self._owns_client = True

    # -- helpers -------------------------------------------------------------

    def _resolve_model(self, request_model: str) -> str:
        return request_model or self._default_model

    def _build_body(self, request: ChatCompletionRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._resolve_model(request.model),
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
        }
        params = request.forwarded_params()
        # Same dialect gap as the OpenAI adapter: the gateway's contract takes
        # OpenAI-classic ``max_tokens`` but current deployments (o-series, gpt-5.x)
        # reject it and require ``max_completion_tokens``. Translate here.
        if "max_tokens" in params and "max_completion_tokens" not in params:
            params["max_completion_tokens"] = params.pop("max_tokens")
        body.update(params)
        if stream:
            body["stream"] = True
        return body

    def _params(self) -> dict[str, str]:
        return {"api-version": self._api_version}

    @staticmethod
    def _map_status(exc: httpx.HTTPStatusError) -> ProviderError:
        code = exc.response.status_code
        try:
            detail = exc.response.json().get("error", {}).get("message") or exc.response.text
        except Exception:  # noqa: BLE001 — error body may not be JSON
            detail = exc.response.text
        detail = (detail or "")[:500]
        if code in (401, 403):
            return ProviderAuthError(_NAME, detail or f"HTTP {code}")
        if code == 429:
            return ProviderRateLimitError(_NAME, detail or "rate limited")
        if code in (400, 404, 422):
            return ProviderBadRequestError(_NAME, detail or f"HTTP {code}")
        return ProviderError(_NAME, f"upstream returned {code}: {detail}")

    def _map_error(self, exc: Exception) -> ProviderError:
        if isinstance(exc, httpx.HTTPStatusError):
            return self._map_status(exc)
        if isinstance(exc, httpx.TimeoutException):
            return ProviderTimeoutError(_NAME, str(exc))
        if isinstance(exc, httpx.HTTPError):
            return ProviderError(_NAME, f"connection error: {exc}")
        log.warning("azure_foundry.unexpected_error", error=str(exc), error_type=type(exc).__name__)
        return ProviderError(_NAME, f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _usage(raw: dict[str, Any] | None) -> NormalizedUsage:
        raw = raw or {}
        prompt = int(raw.get("prompt_tokens") or 0)
        completion = int(raw.get("completion_tokens") or 0)
        total = int(raw.get("total_tokens") or (prompt + completion))
        return NormalizedUsage(
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=total
        )

    # -- interface ---------------------------------------------------------

    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        try:
            resp = await self._client.post(
                "/chat/completions",
                params=self._params(),
                json=self._build_body(request, stream=False),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise self._map_error(exc) from exc
        except Exception as exc:  # provider boundary: always re-raise as a typed error
            raise self._map_error(exc) from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return NormalizedCompletion(
            id=data.get("id") or f"foundry_{uuid.uuid4().hex}",
            created=int(data.get("created") or time.time()),
            model=data.get("model") or self._resolve_model(request.model),
            role=message.get("role") or "assistant",
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            usage=self._usage(data.get("usage")),
            tool_calls=message.get("tool_calls") or None,
            raw=data,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        body = self._build_body(request, stream=True)
        try:
            async with self._client.stream(
                "POST", "/chat/completions", params=self._params(), json=body
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = (choice.get("delta") or {}).get("content") or ""
                    finish = choice.get("finish_reason")
                    usage = self._usage(chunk["usage"]) if chunk.get("usage") else None
                    if delta or finish or usage:
                        yield StreamChunk(
                            delta=delta,
                            finish_reason=finish,
                            usage=usage,
                            response_id=chunk.get("id"),
                            created=chunk.get("created"),
                            model=chunk.get("model"),
                        )
        except httpx.HTTPError as exc:
            raise self._map_error(exc) from exc
        except Exception as exc:  # provider boundary: always re-raise as a typed error
            log.warning("azure_foundry.stream_error", error=str(exc), error_type=type(exc).__name__)
            raise self._map_error(exc) from exc

    async def list_models(self) -> list[ProviderModel]:
        # The inference endpoint has no portable model-listing route; a Foundry
        # resource's deployments are managed in the control plane. Report the
        # configured default deployment so callers see something real.
        return [ProviderModel(id=self._default_model, owned_by=_NAME)]

    async def health_check(self) -> HealthResult:
        start = time.perf_counter()
        # 16, not 1: reasoning deployments spend the completion budget on hidden
        # reasoning tokens and 400 if it can't fit any output.
        probe = {
            "model": self._default_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_completion_tokens": 16,
        }
        try:
            resp = await self._client.post("/chat/completions", params=self._params(), json=probe)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            log.warning("azure_foundry.health_check.failed", error=str(exc))
            return HealthResult(healthy=False, detail=str(exc)[:300])
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return HealthResult(
            healthy=True, latency_ms=latency_ms, checked_models=[self._default_model]
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
