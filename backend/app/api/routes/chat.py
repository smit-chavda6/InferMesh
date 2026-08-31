"""``POST /v1/chat/completions`` — the gateway's core endpoint.

Phase 1 scope: validate, route to a single provider, normalize the response, and
attach ``gateway`` metadata. Retry/backoff/fallback (Phase 3), caching &
rate-limiting (Phase 6), persistence & cost (Phase 4), and streaming (Phase 5)
extend this handler in later phases.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.logging_config import get_logger
from app.providers.registry import ProviderRegistry
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ResponseChoice,
    ResponseMessage,
    Usage,
)
from app.schemas.gateway import CacheInfo, FallbackInfo, GatewayMetadata

router = APIRouter(tags=["gateway"])
log = get_logger(__name__)


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    response_model_exclude_none=True,
)
async def create_chat_completion(
    payload: ChatCompletionRequest, request: Request
) -> ChatCompletionResponse:
    request_id: str = request.state.request_id
    registry: ProviderRegistry = request.app.state.registry

    if payload.stream:
        # Streaming lands in Phase 5; fail loudly rather than silently ignoring it.
        raise HTTPException(status_code=501, detail="streaming is not implemented until Phase 5")

    provider_name = registry.resolve(payload.provider)
    adapter = registry.get(provider_name)

    log.info(
        "chat.dispatch",
        provider=provider_name,
        model=payload.model,
        messages=len(payload.messages),
    )

    started = time.perf_counter()
    result = await adapter.complete(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    log.info(
        "chat.completed",
        provider=provider_name,
        upstream_model=result.model,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
        latency_ms=latency_ms,
    )

    return ChatCompletionResponse(
        id=result.id,
        created=result.created,
        model=payload.model or result.model,
        choices=[
            ResponseChoice(
                index=0,
                message=ResponseMessage(
                    role=result.role,
                    content=result.content,
                    tool_calls=result.tool_calls,
                ),
                finish_reason=result.finish_reason,
            )
        ],
        usage=Usage(**asdict(result.usage)),
        gateway=GatewayMetadata(
            request_id=request_id,
            provider=provider_name,
            model=payload.model or result.model,
            upstream_model=result.model,
            cache=CacheInfo(status="DISABLED"),
            fallback=FallbackInfo(used=False, chain=[]),
            retries=0,
            latency_ms=latency_ms,
        ),
    )
