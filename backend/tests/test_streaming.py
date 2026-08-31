"""Phase 5: SSE streaming for /v1/chat/completions.

DoD: a streamed request delivers incremental chunks and still logs one complete,
accurate usage row once the stream ends.
"""

from __future__ import annotations

import json

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import RequestLog
from app.errors import ProviderError, ProviderTimeoutError
from app.main import create_app
from app.providers.base import StreamChunk
from app.routing import StreamOutcome

from .conftest import make_settings
from .test_routing import StreamingScriptedAdapter, build_router

_BODY = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True}


def _events(sse_text: str) -> list[dict]:
    """Parse `data:` lines (excluding [DONE]) into dicts."""
    out: list[dict] = []
    for line in sse_text.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[len("data: ") :]))
    return out


# --- Router level -------------------------------------------------------


async def test_router_streams_deltas_then_terminal_outcome() -> None:
    router, _ = build_router({"openai": StreamingScriptedAdapter("openai", ["a", "b", "c"])})
    items = [item async for item in router.execute_stream(_req())]

    deltas = [i for i in items if isinstance(i, StreamChunk)]
    outcomes = [i for i in items if isinstance(i, StreamOutcome)]
    assert "".join(d.delta for d in deltas) == "abc"
    assert len(outcomes) == 1
    so = outcomes[0]
    assert so.provider_used == "openai"
    assert so.finish_reason == "stop"
    assert so.usage.total_tokens == 12
    assert so.fallback_used is False


async def test_router_falls_back_before_first_token() -> None:
    router, _ = build_router(
        {
            "openai": StreamingScriptedAdapter(
                "openai", [], fail_before_first=ProviderTimeoutError("openai", "t")
            ),
            "anthropic": StreamingScriptedAdapter("anthropic", ["x", "y"]),
        }
    )
    items = [item async for item in router.execute_stream(_req())]
    so = next(i for i in items if isinstance(i, StreamOutcome))
    assert so.provider_used == "anthropic"
    assert so.fallback_used is True
    assert "".join(i.delta for i in items if isinstance(i, StreamChunk)) == "xy"


async def test_router_midstream_failure_ends_with_error_outcome_no_fallback() -> None:
    an = StreamingScriptedAdapter("anthropic", ["ok"])
    router, _ = build_router(
        {
            "openai": StreamingScriptedAdapter("openai", ["one", "two", "three"], fail_after_n=1),
            "anthropic": an,
        }
    )
    items = [item async for item in router.execute_stream(_req())]
    so = next(i for i in items if isinstance(i, StreamOutcome))
    assert so.error is not None
    assert so.provider_used == "openai"
    # only the first delta made it out before the failure
    assert "".join(i.delta for i in items if isinstance(i, StreamChunk)) == "one"
    assert an.stream_calls == 0  # no fallback once bytes were sent


def _req(**overrides: object):
    from app.schemas.chat import ChatCompletionRequest, ChatMessage

    payload: dict[str, object] = {
        "model": "m",
        "messages": [ChatMessage(role="user", content="hi")],
        "stream": True,
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


# --- HTTP level -------------------------------------------------------


async def test_sse_response_shape_and_done(client: AsyncClient) -> None:
    async with client.stream("POST", "/v1/chat/completions", json=_BODY) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join([c async for c in resp.aiter_text()])

    assert text.rstrip().endswith("data: [DONE]")
    events = _events(text)
    # first event carries the assistant role
    assert events[0]["choices"][0]["delta"] == {"role": "assistant"}
    content = "".join(
        e["choices"][0]["delta"].get("content", "")
        for e in events
        if e["choices"] and e["choices"][0]["delta"].get("content")
    )
    assert content == "Hello from the OpenAI mock."
    # final event has finish_reason + usage + gateway
    final = events[-1]
    assert final["choices"][0]["finish_reason"] == "stop"
    assert final["usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert final["gateway"]["provider"] == "openai"
    assert final["gateway"]["request_id"].startswith("req_")


async def test_streamed_request_logs_one_accurate_usage_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    async with client.stream("POST", "/v1/chat/completions", json=_BODY) as resp:
        text = "".join([c async for c in resp.aiter_text()])
    request_id = _events(text)[-1]["gateway"]["request_id"]

    count = await db_session.scalar(select(func.count()).select_from(RequestLog))
    assert count == 1
    row = (
        await db_session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
    ).scalar_one()
    assert row.streamed is True
    assert row.status == "success"
    assert row.provider == "openai"
    assert (row.prompt_tokens, row.completion_tokens, row.total_tokens) == (11, 7, 18)
    assert row.cost_usd is not None and row.cost_usd > 0
    assert row.finish_reason == "stop"
    assert row.latency_ms >= 0


async def test_pre_stream_failure_is_json_error_not_sse(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        for name in ("openai", "anthropic", "gemini"):
            app.state.registry._adapters[name] = StreamingScriptedAdapter(
                name, [], fail_before_first=ProviderError(name, "down")
            )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
            resp = await http.post("/v1/chat/completions", json=_BODY)

    assert resp.status_code == 502
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["error"]["type"] == "all_providers_failed"

    row = (await db_session.execute(select(RequestLog))).scalar_one()
    assert row.status == "error"
    assert row.streamed is True
    assert row.http_status == 502


async def test_midstream_failure_logs_error_row_with_partial_usage(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    settings = make_settings(retry_base_delay_seconds=0.0, retry_jitter=False)
    app = create_app(settings)
    async with LifespanManager(app):
        app.state.registry._adapters["openai"] = StreamingScriptedAdapter(
            "openai", ["a", "b", "c", "d"], fail_after_n=2
        )
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://gateway.test") as http,
            http.stream("POST", "/v1/chat/completions", json=_BODY) as resp,
        ):
            assert resp.status_code == 200  # SSE already started
            text = "".join([c async for c in resp.aiter_text()])

    assert "data: [DONE]" in text
    events = _events(text)
    assert any("error" in e.get("gateway", {}) for e in events if "gateway" in e)

    row = (await db_session.execute(select(RequestLog))).scalar_one()
    assert row.status == "error"
    assert row.streamed is True
    assert row.error_type == "provider_error"
