"""Shared test fixtures.

The OpenAI and Anthropic SDKs (v3.x / v1.x) talk over ``httpx2``, so those are
mocked at the transport layer with ``httpx2.MockTransport`` — exercising the
adapters' real request-building and response-parsing. The google-genai client is
mocked at the SDK method boundary (it has a more involved transport stack), so
its translation code still runs against a constructed response object.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anthropic
import httpx2
import openai
import pytest
from asgi_lifespan import LifespanManager
from google import genai
from google.genai import types as genai_types
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

os.environ.setdefault("LOG_JSON", "false")

from app.config import Settings
from app.db import models as _models  # noqa: F401  — registers tables on Base.metadata
from app.db.base import Base
from app.main import create_app
from app.providers.anthropic_adapter import AnthropicAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.openai_adapter import OpenAIAdapter

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://gateway:gateway@localhost:5432/gateway_test",
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")

ADMIN_EMAIL = "admin@example.test"
ADMIN_PASSWORD = "admin-test-password"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "log_json": False,
        "openai_api_key": "test-openai-key",
        "openai_mode": "native",
        "anthropic_api_key": "test-anthropic-key",
        "gemini_api_key": "test-gemini-key",
        "default_provider": "openai",
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "semantic_cache_enabled": False,  # no embedding key in tests; exact-match only
        "retry_base_delay_seconds": 0.0,
        "retry_jitter": False,
        # Phase 6 features are opt-in per test (they add Redis state to manage).
        "rate_limit_enabled": False,
        "cache_enabled": False,
        "fx_enabled": False,  # no outbound FX fetch in the offline suite
        # Phase 8 admin auth
        "jwt_secret": "test-jwt-secret-that-is-at-least-32-chars-long",
        "admin_email": ADMIN_EMAIL,
        "admin_password": ADMIN_PASSWORD,
        "auth_cookie_secure": False,
        "bcrypt_rounds": 4,  # keep the test suite fast
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def admin_cookies(app: object) -> dict[str, str]:
    """Admin session cookie (mints an access token directly).

    A cookie, not an ``Authorization`` header, because the gateway chat endpoint
    reads ``Authorization: Bearer`` as a *client API key* — the two auth systems
    share that header and must not collide.
    """
    token = app.state.admin_auth.issue(subject=ADMIN_EMAIL).access  # type: ignore[attr-defined]
    return {"gw_access": token}


# --- Database fixtures -----------------------------------------------------


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Fresh ``requests`` schema in the test database; skips if it is unreachable."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001 - DB not running locally -> skip, don't hard-fail
        await engine.dispose()
        pytest.skip(f"test database not reachable at {TEST_DATABASE_URL}: {exc}")
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def redis_ready():
    """Flush the test Redis DB before/after; skip if Redis is unreachable."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(TEST_REDIS_URL, decode_responses=True, socket_connect_timeout=2.0)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        await client.aclose()
        pytest.skip(f"test Redis not reachable at {TEST_REDIS_URL}: {exc}")
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


# --- OpenAI mock ------------------------------------------------------------

CHAT_COMPLETION_FIXTURE = {
    "id": "chatcmpl-test123",
    "object": "chat.completion",
    "created": 1_700_000_000,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from the OpenAI mock."},
            "finish_reason": "stop",
            "logprobs": None,
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}

OPENAI_MODELS_FIXTURE = {
    "object": "list",
    "data": [
        {"id": "gpt-4o-mini", "object": "model", "created": 1_700_000_000, "owned_by": "system"},
        {"id": "gpt-4o", "object": "model", "created": 1_700_000_000, "owned_by": "system"},
    ],
}


_OPENAI_STREAM_DELTAS = ["Hello", " from", " the", " OpenAI", " mock."]


def _openai_stream_body() -> bytes:
    base = {
        "id": "chatcmpl-test123",
        "object": "chat.completion.chunk",
        "created": 1_700_000_000,
        "model": "gpt-4o-mini-2024-07-18",
    }
    lines: list[str] = []

    def frame(delta: dict, finish: str | None, *, choices: bool = True) -> str:
        obj = {**base, "choices": []}
        if choices:
            obj["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
        return f"data: {json.dumps(obj)}\n\n"

    lines.append(frame({"role": "assistant"}, None))
    for d in _OPENAI_STREAM_DELTAS:
        lines.append(frame({"content": d}, None))
    lines.append(frame({}, "stop"))
    usage_obj = {
        **base,
        "choices": [],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    lines.append(f"data: {json.dumps(usage_obj)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _openai_handler(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/chat/completions"):
        body = request.content or b""
        if b'"stream": true' in body or b'"stream":true' in body:
            return httpx2.Response(
                200,
                content=_openai_stream_body(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(200, json=CHAT_COMPLETION_FIXTURE)
    if path.endswith("/models"):
        return httpx2.Response(200, json=OPENAI_MODELS_FIXTURE)
    return httpx2.Response(404, json={"error": {"message": f"unmocked path {path}"}})


def new_mock_openai_client() -> openai.AsyncOpenAI:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(_openai_handler))
    return openai.AsyncOpenAI(api_key="test-key", http_client=http_client, max_retries=0)


@pytest.fixture
def mock_openai_client() -> openai.AsyncOpenAI:
    return new_mock_openai_client()


@pytest.fixture
def mock_adapter(mock_openai_client: openai.AsyncOpenAI) -> OpenAIAdapter:
    return OpenAIAdapter(make_settings(), client=mock_openai_client)


# --- Anthropic mock -------------------------------------------------------

ANTHROPIC_MESSAGE_FIXTURE = {
    "id": "msg_test123",
    "type": "message",
    "role": "assistant",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "Hello from the Anthropic mock."}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 13, "output_tokens": 9},
}

ANTHROPIC_MODELS_FIXTURE = {
    "data": [
        {
            "id": "claude-3-5-sonnet-20241022",
            "type": "model",
            "display_name": "Claude 3.5 Sonnet",
            "created_at": "2024-10-22T00:00:00Z",
        }
    ],
    "has_more": False,
    "first_id": "claude-3-5-sonnet-20241022",
    "last_id": "claude-3-5-sonnet-20241022",
}


_ANTHROPIC_STREAM_DELTAS = ["Hello", " from", " the", " Anthropic", " mock."]


def _anthropic_stream_body() -> bytes:
    def ev(kind: str, data: dict) -> str:
        return f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n"

    parts = [
        ev(
            "message_start",
            {
                "message": {
                    "id": "msg_test123",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-3-5-sonnet-20241022",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 13, "output_tokens": 1},
                }
            },
        ),
        ev("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
    ]
    for d in _ANTHROPIC_STREAM_DELTAS:
        parts.append(
            ev("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": d}})
        )
    parts += [
        ev("content_block_stop", {"index": 0}),
        ev(
            "message_delta",
            {
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 9},
            },
        ),
        ev("message_stop", {}),
    ]
    return "".join(parts).encode()


def _anthropic_handler(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/v1/messages"):
        body = request.content or b""
        if b'"stream": true' in body or b'"stream":true' in body:
            return httpx2.Response(
                200,
                content=_anthropic_stream_body(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(200, json=ANTHROPIC_MESSAGE_FIXTURE)
    if path.endswith("/v1/models"):
        return httpx2.Response(200, json=ANTHROPIC_MODELS_FIXTURE)
    return httpx2.Response(404, json={"type": "error", "error": {"message": f"unmocked {path}"}})


def new_mock_anthropic_client() -> anthropic.AsyncAnthropic:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(_anthropic_handler))
    return anthropic.AsyncAnthropic(api_key="test-key", http_client=http_client, max_retries=0)


@pytest.fixture
def mock_anthropic_client() -> anthropic.AsyncAnthropic:
    return new_mock_anthropic_client()


@pytest.fixture
def mock_anthropic_adapter(mock_anthropic_client: anthropic.AsyncAnthropic) -> AnthropicAdapter:
    return AnthropicAdapter(make_settings(), client=mock_anthropic_client)


# --- Gemini mock ---------------------------------------------------------

GEMINI_RESPONSE = genai_types.GenerateContentResponse.model_validate(
    {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": "Hello from the Gemini mock."}]},
                "finish_reason": "STOP",
            }
        ],
        "usage_metadata": {
            "prompt_token_count": 6,
            "candidates_token_count": 5,
            "thoughts_token_count": 4,
            "total_token_count": 15,
        },
        "response_id": "resp-test123",
        "model_version": "gemini-3.6-flash",
    }
)


GEMINI_STREAM_DELTAS = ["Hello", " from", " the", " Gemini", " mock."]


def _gemini_stream_parts() -> list[genai_types.GenerateContentResponse]:
    parts: list[genai_types.GenerateContentResponse] = []
    for d in GEMINI_STREAM_DELTAS:
        parts.append(
            genai_types.GenerateContentResponse.model_validate(
                {
                    "candidates": [{"content": {"role": "model", "parts": [{"text": d}]}}],
                    "response_id": "resp-test123",
                    "model_version": "gemini-3.6-flash",
                }
            )
        )
    parts.append(
        genai_types.GenerateContentResponse.model_validate(
            {
                "candidates": [{"finish_reason": "STOP"}],
                "usage_metadata": {
                    "prompt_token_count": 6,
                    "candidates_token_count": 5,
                    "thoughts_token_count": 4,
                    "total_token_count": 15,
                },
                "response_id": "resp-test123",
                "model_version": "gemini-3.6-flash",
            }
        )
    )
    return parts


def make_gemini_adapter(
    response: genai_types.GenerateContentResponse | None = None,
    error: Exception | None = None,
    stream_parts: list[genai_types.GenerateContentResponse] | None = None,
    stream_error: Exception | None = None,
) -> GeminiAdapter:
    adapter = GeminiAdapter(make_settings(), client=genai.Client(api_key="test-key"))

    async def fake_generate_content(**_kwargs: object) -> genai_types.GenerateContentResponse:
        if error is not None:
            raise error
        return response or GEMINI_RESPONSE

    async def fake_generate_content_stream(**_kwargs: object):  # type: ignore[no-untyped-def]
        # Real SDK: `await ...generate_content_stream(...)` -> async iterator.
        if stream_error is not None:
            raise stream_error
        parts = stream_parts if stream_parts is not None else _gemini_stream_parts()

        async def _gen():  # type: ignore[no-untyped-def]
            for part in parts:
                yield part

        return _gen()

    adapter._client.aio.models.generate_content = fake_generate_content  # type: ignore[method-assign]
    adapter._client.aio.models.generate_content_stream = fake_generate_content_stream  # type: ignore[method-assign]
    return adapter


@pytest.fixture
def mock_gemini_adapter() -> GeminiAdapter:
    return make_gemini_adapter()


# --- Full gateway (all three providers mocked) --------------------------


@pytest.fixture
async def app_with_mocks(
    db_engine: AsyncEngine,
    redis_ready,
    mock_openai_client: openai.AsyncOpenAI,
    mock_anthropic_client: anthropic.AsyncAnthropic,
):
    """A fully-wired app with all three providers mocked and the test DB + Redis attached."""
    settings = make_settings()
    application = create_app(settings)
    async with LifespanManager(application):
        registry = application.state.registry
        registry._adapters["openai"] = OpenAIAdapter(settings, client=mock_openai_client)
        registry._adapters["anthropic"] = AnthropicAdapter(settings, client=mock_anthropic_client)
        registry._adapters["gemini"] = make_gemini_adapter()
        yield application


@pytest.fixture
async def client(app_with_mocks) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app_with_mocks)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
        yield http_client


@pytest.fixture
async def admin_client(app_with_mocks) -> AsyncIterator[AsyncClient]:
    """Like ``client`` but carries a valid admin session cookie."""
    transport = ASGITransport(app=app_with_mocks)
    async with AsyncClient(
        transport=transport,
        base_url="http://gateway.test",
        cookies=admin_cookies(app_with_mocks),
    ) as http_client:
        yield http_client


@asynccontextmanager
async def make_app(**settings_overrides: object):
    """Build a fully-wired app (all three providers mocked) with custom settings.

    Caller is responsible for ensuring db_engine / redis_ready fixtures ran.
    """
    settings = make_settings(**settings_overrides)
    application = create_app(settings)
    async with LifespanManager(application):
        reg = application.state.registry
        reg._adapters["openai"] = OpenAIAdapter(settings, client=new_mock_openai_client())
        reg._adapters["anthropic"] = AnthropicAdapter(settings, client=new_mock_anthropic_client())
        reg._adapters["gemini"] = make_gemini_adapter()
        yield application


def http_for(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")


async def seed_requests(session, n: int = 60) -> None:
    """Insert synthetic ``requests`` rows so aggregation endpoints return real numbers."""
    import datetime as _dt
    from decimal import Decimal

    from app.db.models import RequestLog

    now = _dt.datetime.now(_dt.UTC)
    providers = ("openai", "anthropic", "gemini")
    for i in range(n):
        p = providers[i % 3]
        ok = i % 7 != 0
        session.add(
            RequestLog(
                request_id=f"req_seed_{i:04d}",
                created_at=now - _dt.timedelta(minutes=i * 3),
                provider=p,
                model=f"{p}-model",
                upstream_model=f"{p}-model-2026",
                status="success" if ok else "error",
                http_status=200 if ok else 502,
                error_type=None if ok else "provider_error",
                latency_ms=100.0 + (i % 20) * 15,
                prompt_tokens=10 + i,
                completion_tokens=5 + i,
                total_tokens=15 + 2 * i,
                cost_usd=Decimal("0.001000") if ok else None,
                input_cost_usd=Decimal("0.000400") if ok else None,
                output_cost_usd=Decimal("0.000600") if ok else None,
                pricing_version="test" if ok else None,
                cache_status="HIT" if i % 5 == 0 else "MISS",
                cache_saved_usd=Decimal("0.001000") if i % 5 == 0 else None,
                fallback_used=(i % 9 == 0),
                retries=1 if i % 9 == 0 else 0,
                message_count=1 + (i % 3),
            )
        )
    await session.commit()
