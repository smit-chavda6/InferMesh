"""``POST /v1/chat/completions`` — the gateway's core endpoint.

Flow: validate -> run through the provider router (retry + backoff + fallback) ->
normalize the response + attach ``gateway`` metadata -> record exactly one usage
row (on both the success and error paths). Caching & rate-limiting (Phase 6) and
streaming (Phase 5) extend this handler later.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.errors import GatewayError
from app.logging_config import get_logger
from app.observability import RequestOutcome, UsageRecorder
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
    recorder: UsageRecorder = request.app.state.recorder

    if payload.stream:
        # Streaming lands in Phase 5; fail loudly rather than silently ignoring it.
        raise HTTPException(status_code=501, detail="streaming is not implemented until Phase 5")

    outcome = RequestOutcome(
        request_id=request_id,
        model=payload.model,
        message_count=len(payload.messages),
        requested_provider=payload.provider,
    )
    started = time.perf_counter()

    log.info(
        "chat.dispatch",
        requested_provider=payload.provider,
        model=payload.model,
        messages=len(payload.messages),
    )

    try:
        result = await gateway_router.execute(payload)
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)

        completion = result.completion
        chain = [a.model_dump(exclude_none=True) for a in result.attempts]

        outcome.status = "success"
        outcome.http_status = 200
        outcome.provider = result.provider_used
        outcome.upstream_model = completion.model
        outcome.prompt_tokens = completion.usage.prompt_tokens
        outcome.completion_tokens = completion.usage.completion_tokens
        outcome.total_tokens = completion.usage.total_tokens
        outcome.finish_reason = completion.finish_reason
        outcome.fallback_used = result.fallback_used
        outcome.retries = result.total_retries
        outcome.provider_chain = chain

        log.info(
            "chat.completed",
            provider=result.provider_used,
            upstream_model=completion.model,
            fallback_used=result.fallback_used,
            total_retries=result.total_retries,
            prompt_tokens=completion.usage.prompt_tokens,
            completion_tokens=completion.usage.completion_tokens,
            latency_ms=outcome.latency_ms,
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
                latency_ms=outcome.latency_ms,
            ),
        )
    except GatewayError as exc:
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        outcome.status = "error"
        outcome.http_status = exc.status_code
        outcome.error_type = exc.error_type
        outcome.error_message = exc.message

        attempts = getattr(exc, "attempts", None)
        if attempts:
            outcome.provider_chain = [a.model_dump(exclude_none=True) for a in attempts]
            outcome.provider = attempts[-1].provider
            outcome.fallback_used = len({a.provider for a in attempts}) > 1
            outcome.retries = sum(a.retries for a in attempts)
        raise
    finally:
        await recorder.record(outcome)
