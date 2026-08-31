"""``POST /v1/chat/completions`` — the gateway's core endpoint.

Pipeline: resolve caller (API key) -> rate-limit check -> cache lookup ->
router (retry + backoff + fallback) -> normalize + ``gateway`` metadata ->
cache store -> record exactly one usage row.

Non-streaming returns a JSON body; ``"stream": true`` returns Server-Sent Events
of OpenAI-compatible ``chat.completion.chunk`` frames, a final frame with
``finish_reason`` / ``usage`` / ``gateway``, then ``data: [DONE]``. Streamed
requests are never served from or written to the cache.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import Caller, CallerDep
from app.cache import CachedResponse, ChatCache
from app.errors import GatewayError, RateLimitExceededError
from app.logging_config import get_logger
from app.observability import RequestOutcome, UsageRecorder
from app.ratelimit import RateLimiter
from app.routing import Router, StreamOutcome
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


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


@router.post("/v1/chat/completions", response_model=None)
async def create_chat_completion(
    payload: ChatCompletionRequest, request: Request, caller: CallerDep
) -> JSONResponse | StreamingResponse:
    request_id: str = request.state.request_id
    gateway_router: Router = request.app.state.router
    recorder: UsageRecorder = request.app.state.recorder
    cache: ChatCache = request.app.state.cache
    settings = request.app.state.settings

    outcome = RequestOutcome(
        request_id=request_id,
        model=payload.model,
        message_count=len(payload.messages),
        requested_provider=payload.provider,
        streamed=payload.stream,
        project_id=str(caller.project.id) if caller.project else None,
        project_name=caller.project_name,
        api_key_prefix=caller.api_key_prefix,
    )
    started = time.perf_counter()

    log.info(
        "chat.dispatch",
        requested_provider=payload.provider,
        model=payload.model,
        messages=len(payload.messages),
        stream=payload.stream,
        project=caller.project_name or "anon",
    )

    if settings.rate_limit_enabled:
        await _enforce_rate_limit(
            request.app.state.rate_limiter, caller, outcome, recorder, started
        )

    if payload.stream:
        return await _stream_response(
            payload, request_id, gateway_router, recorder, outcome, started
        )

    # --- cache lookup ---
    lookup = await cache.lookup(payload)
    if lookup.hit and lookup.response is not None:
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return await _cache_hit_response(payload, request_id, lookup, outcome, recorder)
    outcome.cache_key = lookup.key

    try:
        result = await gateway_router.execute(payload)
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)

        completion = result.completion
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
        outcome.provider_chain = [a.model_dump(exclude_none=True) for a in result.attempts]
        cache_active = lookup.key is not None
        outcome.cache_status = "MISS" if cache_active else "DISABLED"

        cost = request.app.state.pricing.cost(
            result.provider_used,
            payload.model,
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
        )

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

        cached = CachedResponse(
            id=completion.id,
            created=completion.created,
            provider=result.provider_used,
            model=completion.model,
            role=completion.role,
            content=completion.content,
            finish_reason=completion.finish_reason,
            usage=asdict(completion.usage),
            tool_calls=completion.tool_calls,
            cost_usd=float(cost.total_cost_usd) if cost else None,
            input_cost_usd=float(cost.input_cost_usd) if cost else None,
            output_cost_usd=float(cost.output_cost_usd) if cost else None,
            pricing_version=cost.pricing_version if cost else None,
        )
        await cache.store(payload, lookup.key, cached)

        response = ChatCompletionResponse(
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
                cache=CacheInfo(status="MISS" if cache_active else "DISABLED", key=lookup.key),
                fallback=FallbackInfo(used=result.fallback_used, chain=result.attempts),
                retries=result.total_retries,
                latency_ms=outcome.latency_ms,
                cost_usd=float(cost.total_cost_usd) if cost else None,
            ),
        )
        return JSONResponse(content=jsonable_encoder(response, exclude_none=True))
    except GatewayError as exc:
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _apply_error(outcome, exc)
        raise
    finally:
        await recorder.record(outcome)


async def _enforce_rate_limit(
    limiter: RateLimiter,
    caller: Caller,
    outcome: RequestOutcome,
    recorder: UsageRecorder,
    started: float,
) -> None:
    rl = await limiter.check(
        caller.identifier, caller.rate_limit_per_minute, caller.rate_limit_window_seconds
    )
    if rl.allowed:
        return
    outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    exc = RateLimitExceededError(
        f"rate limit exceeded: {rl.limit} requests / {caller.rate_limit_window_seconds}s",
        limit=rl.limit,
        retry_after=rl.retry_after,
    )
    _apply_error(outcome, exc)
    await recorder.record(outcome)
    raise exc


async def _cache_hit_response(
    payload: ChatCompletionRequest,
    request_id: str,
    lookup: Any,
    outcome: RequestOutcome,
    recorder: UsageRecorder,
) -> JSONResponse:
    cr: CachedResponse = lookup.response
    outcome.status = "success"
    outcome.http_status = 200
    outcome.provider = cr.provider
    outcome.upstream_model = cr.model
    outcome.prompt_tokens = cr.usage.get("prompt_tokens", 0)
    outcome.completion_tokens = cr.usage.get("completion_tokens", 0)
    outcome.total_tokens = cr.usage.get("total_tokens", 0)
    outcome.finish_reason = cr.finish_reason
    outcome.cache_status = "HIT"
    outcome.cache_key = lookup.key
    if cr.cost_usd is not None:
        outcome.precomputed_cost = (
            cr.input_cost_usd or 0.0,
            cr.output_cost_usd or 0.0,
            cr.cost_usd,
            cr.pricing_version or "",
        )

    log.info("chat.cache_hit", kind=lookup.kind, provider=cr.provider, model=payload.model)

    body = ChatCompletionResponse(
        id=cr.id,
        created=cr.created,
        model=payload.model or cr.model,
        choices=[
            ResponseChoice(
                index=0,
                message=ResponseMessage(role=cr.role, content=cr.content, tool_calls=cr.tool_calls),
                finish_reason=cr.finish_reason,
            )
        ],
        usage=Usage(**cr.usage),
        gateway=GatewayMetadata(
            request_id=request_id,
            provider=cr.provider,
            model=payload.model or cr.model,
            upstream_model=cr.model,
            cache=CacheInfo(status="HIT", kind=lookup.kind.lower(), key=lookup.key),
            fallback=FallbackInfo(used=False, chain=[]),
            retries=0,
            latency_ms=outcome.latency_ms,
            cost_usd=0.0,
        ),
    )
    await recorder.record(outcome)
    return JSONResponse(content=jsonable_encoder(body, exclude_none=True))


def _apply_error(outcome: RequestOutcome, exc: GatewayError) -> None:
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


async def _stream_response(
    payload: ChatCompletionRequest,
    request_id: str,
    gateway_router: Router,
    recorder: UsageRecorder,
    outcome: RequestOutcome,
    started: float,
) -> StreamingResponse:
    gen = gateway_router.execute_stream(payload)

    # Pull the first item here so a pre-stream failure becomes a JSON error
    # (no SSE body started yet) rather than a broken event stream.
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        first = None
    except GatewayError as exc:
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _apply_error(outcome, exc)
        await recorder.record(outcome)
        raise

    model_name = payload.model

    async def event_stream() -> AsyncIterator[str]:
        stream_outcome: StreamOutcome | None = None
        emitted_role = False
        try:
            item = first
            while item is not None:
                if isinstance(item, StreamOutcome):
                    stream_outcome = item
                    break
                if not emitted_role:
                    yield _sse(_chunk_frame(request_id, model_name, {"role": "assistant"}, None))
                    emitted_role = True
                if item.delta:
                    yield _sse(_chunk_frame(request_id, model_name, {"content": item.delta}, None))
                try:
                    item = await gen.__anext__()
                except StopAsyncIteration:
                    item = None

            if stream_outcome is not None:
                _finalize_outcome(outcome, stream_outcome, started)
                final = _chunk_frame(request_id, model_name, {}, stream_outcome.finish_reason)
                final["usage"] = {
                    "prompt_tokens": stream_outcome.usage.prompt_tokens,
                    "completion_tokens": stream_outcome.usage.completion_tokens,
                    "total_tokens": stream_outcome.usage.total_tokens,
                }
                final["gateway"] = GatewayMetadata(
                    request_id=request_id,
                    provider=stream_outcome.provider_used,
                    model=model_name or stream_outcome.upstream_model,
                    upstream_model=stream_outcome.upstream_model,
                    cache=CacheInfo(status="DISABLED"),
                    fallback=FallbackInfo(
                        used=stream_outcome.fallback_used, chain=stream_outcome.attempts
                    ),
                    retries=stream_outcome.total_retries,
                    latency_ms=outcome.latency_ms,
                ).model_dump(exclude_none=True)
                if stream_outcome.error is not None:
                    final["gateway"]["error"] = {
                        "type": stream_outcome.error.error_type,
                        "message": stream_outcome.error.message,
                    }
                yield _sse(final)
            yield "data: [DONE]\n\n"
        except GatewayError as exc:
            outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            _apply_error(outcome, exc)
            yield _sse({"error": {"type": exc.error_type, "message": exc.message}})
            yield "data: [DONE]\n\n"
        finally:
            await recorder.record(outcome)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chunk_frame(
    request_id: str, model: str, delta: dict[str, Any], finish_reason: str | None
) -> dict[str, Any]:
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _finalize_outcome(outcome: RequestOutcome, so: StreamOutcome, started: float) -> None:
    outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    outcome.provider = so.provider_used
    outcome.upstream_model = so.upstream_model
    outcome.prompt_tokens = so.usage.prompt_tokens
    outcome.completion_tokens = so.usage.completion_tokens
    outcome.total_tokens = so.usage.total_tokens
    outcome.finish_reason = so.finish_reason
    outcome.fallback_used = so.fallback_used
    outcome.retries = so.total_retries
    outcome.provider_chain = [a.model_dump(exclude_none=True) for a in so.attempts]
    if so.error is not None:
        outcome.status = "error"
        outcome.http_status = so.error.status_code
        outcome.error_type = so.error.error_type
        outcome.error_message = so.error.message
    else:
        outcome.status = "success"
        outcome.http_status = 200
