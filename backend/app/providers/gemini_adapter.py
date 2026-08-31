"""Google Gemini provider adapter (google-genai SDK).

Translates the gateway's OpenAI-compatible request into ``generate_content`` and
normalizes the response. The SDK's own retry loop is pinned to a single attempt
so the gateway owns retry/backoff/fallback.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

# Gemini FinishReason name -> OpenAI finish_reason
_FINISH_REASON = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
    "IMAGE_SAFETY": "content_filter",
    "MALFORMED_FUNCTION_CALL": "tool_calls",
}


class GeminiAdapter(ProviderAdapter):
    name = "gemini"

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self._settings = settings
        if client is not None:
            self._client: genai.Client = client
        elif not settings.gemini_api_key:
            raise ProviderNotConfiguredError("gemini", "GEMINI_API_KEY is not set")
        else:
            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=genai_types.HttpOptions(
                    timeout=int(settings.gemini_timeout_seconds * 1000),  # milliseconds
                    retry_options=genai_types.HttpRetryOptions(attempts=1),
                ),
            )

    # -- helpers ------------------------------------------------------------

    def _resolve_model(self, request_model: str) -> str:
        return request_model or self._settings.gemini_default_model

    def _build_contents(
        self, request: ChatCompletionRequest
    ) -> tuple[str | None, list[genai_types.Content]]:
        system, turns = split_system_and_turns(request.messages)
        contents: list[genai_types.Content] = []
        for message in turns:
            role = "model" if message.role == "assistant" else "user"
            contents.append(
                genai_types.Content(
                    role=role, parts=[genai_types.Part(text=text_of(message.content))]
                )
            )
        return system, contents

    def _build_config(
        self, request: ChatCompletionRequest, system: str | None
    ) -> genai_types.GenerateContentConfig:
        stop = None
        if request.stop is not None:
            stop = [request.stop] if isinstance(request.stop, str) else request.stop
        return genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=request.temperature,
            top_p=request.top_p,
            max_output_tokens=request.max_tokens,
            stop_sequences=stop,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _map_error(self, exc: Exception) -> ProviderError:
        code = getattr(exc, "code", None)
        if isinstance(exc, genai_errors.ClientError):
            if code == 429:
                return ProviderRateLimitError("gemini", str(exc))
            if code in (401, 403):
                return ProviderAuthError("gemini", str(exc))
            if code in (400, 404):
                return ProviderBadRequestError("gemini", str(exc))
            return ProviderError("gemini", f"upstream returned {code}: {exc}")
        if isinstance(exc, genai_errors.ServerError):
            return ProviderError("gemini", f"upstream returned {code}: {exc}")
        if isinstance(exc, TimeoutError):
            return ProviderTimeoutError("gemini", str(exc))
        log.warning("gemini.unexpected_error", error=str(exc), error_type=type(exc).__name__)
        return ProviderError("gemini", f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _usage(um: genai_types.GenerateContentResponseUsageMetadata | None) -> NormalizedUsage:
        if um is None:
            return NormalizedUsage()
        prompt = um.prompt_token_count or 0
        total = um.total_token_count or 0
        # completion covers visible output *and* thinking tokens (both billed).
        completion = max(total - prompt, 0) if total else (um.candidates_token_count or 0)
        return NormalizedUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total or (prompt + completion),
        )

    # -- interface --------------------------------------------------------

    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        system, contents = self._build_contents(request)
        config = self._build_config(request, system)
        model = self._resolve_model(request.model)
        try:
            resp = await self._client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            raise self._map_error(exc) from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError("gemini", str(exc)) from exc
        except Exception as exc:  # provider boundary: always re-raise as a typed error
            raise self._map_error(exc) from exc

        try:
            content = resp.text
        except Exception as exc:  # noqa: BLE001 — some blocked responses raise on .text
            log.warning("gemini.text_extraction_failed", error=str(exc))
            content = None

        finish_reason = None
        if resp.candidates:
            raw_reason = getattr(resp.candidates[0].finish_reason, "name", None)
            finish_reason = _FINISH_REASON.get(raw_reason or "", (raw_reason or "").lower() or None)

        created = int(time.time())
        if resp.create_time is not None:
            created = int(resp.create_time.timestamp())

        return NormalizedCompletion(
            id=resp.response_id or f"gen_{uuid.uuid4().hex}",
            created=created,
            model=resp.model_version or model,
            role="assistant",
            content=content,
            finish_reason=finish_reason,
            usage=self._usage(resp.usage_metadata),
            raw=resp.model_dump(mode="json", exclude_none=True),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        system, contents = self._build_contents(request)
        config = self._build_config(request, system)
        model = self._resolve_model(request.model)
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            async for part in stream:
                try:
                    text = part.text
                except Exception:  # noqa: BLE001 — blocked parts can raise on .text
                    text = None

                finish_reason = None
                if part.candidates:
                    raw = getattr(part.candidates[0].finish_reason, "name", None)
                    finish_reason = _FINISH_REASON.get(raw or "", (raw or "").lower() or None)

                usage = self._usage(part.usage_metadata) if part.usage_metadata else None

                if text or finish_reason or usage:
                    yield StreamChunk(
                        delta=text or "",
                        finish_reason=finish_reason,
                        usage=usage,
                        response_id=part.response_id,
                        model=part.model_version,
                    )
        except genai_errors.APIError as exc:
            raise self._map_error(exc) from exc
        except Exception as exc:  # provider boundary: always re-raise as a typed error
            log.warning("gemini.stream_error", error=str(exc), error_type=type(exc).__name__)
            raise self._map_error(exc) from exc

    async def list_models(self) -> list[ProviderModel]:
        try:
            models: list[ProviderModel] = []
            pager = await self._client.aio.models.list()
            async for m in pager:
                actions = getattr(m, "supported_actions", None) or []
                if actions and "generateContent" not in actions:
                    continue
                model_id = (m.name or "").removeprefix("models/")
                models.append(ProviderModel(id=model_id, owned_by="google"))
            return models
        except genai_errors.APIError as exc:
            raise self._map_error(exc) from exc

    async def health_check(self) -> HealthResult:
        start = time.perf_counter()
        try:
            pager = await self._client.aio.models.list()
            seen: list[str] = []
            async for m in pager:
                seen.append((m.name or "").removeprefix("models/"))
                if len(seen) >= 5:
                    break
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            log.warning("gemini.health_check.failed", error=str(exc))
            return HealthResult(healthy=False, detail=str(exc))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return HealthResult(healthy=True, latency_ms=latency_ms, checked_models=seen)

    async def aclose(self) -> None:
        # google-genai's async client has no explicit close; nothing to release.
        return None
