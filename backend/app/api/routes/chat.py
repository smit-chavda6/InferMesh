"""``POST /v1/chat/completions`` — the gateway's core endpoint.

Current scope: validate, run the request through the provider router (retry +
backoff + fallback), normalize the response, and attach ``gateway`` metadata
describing how it was actually served. Caching & rate-limiting (Phase 6),
persistence & cost (Phase 4), and streaming (Phase 5) extend this handler later.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.logging_config import get_logger
from app.routing import Router
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
    gateway_router: Router = request.app.state.router

    if payload.stream:
        # Streaming lands in Phase 5; fail loudly rather than silently ignoring it.
        raise HTTPException(status_code=501, detail="streaming is not implemented until Phase 5")

    log.info(
        "chat.dispatch",
        requested_provider=payload.provider,
        model=payload.model,
        messages=len(payload.messages),
    )

    started = time.perf_counter()
    result = await gateway_router.execute(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    completion = result.completion
    log.info(
        "chat.completed",
        provider=result.provider_used,
        upstream_model=completion.model,
        fallback_used=result.fallback_used,
        total_retries=result.total_retries,
        prompt_tokens=completion.usage.prompt_tokens,
        completion_tokens=completion.usage.completion_tokens,
        latency_ms=latency_ms,
    )

    return ChatCompletionResponse(
        id=completion.id,
        created=completion.created,
        model=payload.model or completion.model,
        choices=[
            ResponseChoice(
                index=0,
                message=ResponseMessage(
                    role=completion.role,
                    content=completion.content,
                    tool_calls=completion.tool_calls,
                ),
                finish_reason=completion.finish_reason,
            )
        ],
        usage=Usage(**asdict(completion.usage)),
        gateway=GatewayMetadata(
            request_id=request_id,
            provider=result.provider_used,
            model=payload.model or completion.model,
            upstream_model=completion.model,
            cache=CacheInfo(status="DISABLED"),
            fallback=FallbackInfo(used=result.fallback_used, chain=result.attempts),
            retries=result.total_retries,
            latency_ms=latency_ms,
        ),
    )
