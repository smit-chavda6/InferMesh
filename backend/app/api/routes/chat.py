"""``POST /v1/chat/completions`` — the gateway's core endpoint.

Non-streaming: validate -> router (retry + backoff + fallback) -> normalized body
+ ``gateway`` metadata.

Streaming (``"stream": true``): Server-Sent Events of OpenAI-compatible
``chat.completion.chunk`` objects; the final chunk carries ``finish_reason``,
``usage`` and the ``gateway`` object, followed by ``data: [DONE]``.

Both paths record exactly one usage row (Phase 4) — for streams, once the stream
ends (or the client disconnects).
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

from app.errors import GatewayError
from app.logging_config import get_logger
from app.observability import RequestOutcome, UsageRecorder
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
    payload: ChatCompletionRequest, request: Request
) -> JSONResponse | StreamingResponse:
    request_id: str = request.state.request_id
    gateway_router: Router = request.app.state.router
    recorder: UsageRecorder = request.app.state.recorder

    outcome = RequestOutcome(
        request_id=request_id,
        model=payload.model,
        message_count=len(payload.messages),
        requested_provider=payload.provider,
        streamed=payload.stream,
    )
    started = time.perf_counter()

    log.info(
        "chat.dispatch",
        requested_provider=payload.provider,
        model=payload.model,
        messages=len(payload.messages),
        stream=payload.stream,
    )

    if payload.stream:
        return await _stream_response(
            payload, request_id, gateway_router, recorder, outcome, started
        )

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
                cache=CacheInfo(status="DISABLED"),
                fallback=FallbackInfo(used=result.fallback_used, chain=result.attempts),
                retries=result.total_retries,
                latency_ms=outcome.latency_ms,
            ),
        )
        return JSONResponse(content=jsonable_encoder(response, exclude_none=True))
    except GatewayError as exc:
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _apply_error(outcome, exc)
        raise
    finally:
        await recorder.record(outcome)


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
                # StreamChunk
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
                final = _chunk_frame(
                    request_id,
                    model_name,
                    {},
                    stream_outcome.finish_reason,
                )
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
            # Pre-first-token failure surfaced during iteration.
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
