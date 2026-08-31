"""Shared test fixtures.

The OpenAI SDK (v3.x) talks over ``httpx2``, so we mock at the transport layer
with ``httpx2.MockTransport``. This exercises the adapter's real request-building
and response-parsing paths without touching the network.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx2
import openai
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LOG_JSON", "false")

from app.config import Settings
from app.main import create_app
from app.providers.openai_adapter import OpenAIAdapter


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "log_json": False,
        "openai_api_key": "test-key",
        "openai_mode": "native",
        "default_provider": "openai",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


CHAT_COMPLETION_FIXTURE = {
    "id": "chatcmpl-test123",
    "object": "chat.completion",
    "created": 1_700_000_000,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from the mock provider."},
            "finish_reason": "stop",
            "logprobs": None,
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}

MODELS_FIXTURE = {
    "object": "list",
    "data": [
        {"id": "gpt-4o-mini", "object": "model", "created": 1_700_000_000, "owned_by": "system"},
        {"id": "gpt-4o", "object": "model", "created": 1_700_000_000, "owned_by": "system"},
    ],
}


def _mock_handler(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/chat/completions"):
        return httpx2.Response(200, json=CHAT_COMPLETION_FIXTURE)
    if path.endswith("/models"):
        return httpx2.Response(200, json=MODELS_FIXTURE)
    return httpx2.Response(404, json={"error": {"message": f"unmocked path {path}"}})


@pytest.fixture
def mock_openai_client() -> openai.AsyncOpenAI:
    transport = httpx2.MockTransport(_mock_handler)
    http_client = httpx2.AsyncClient(transport=transport)
    return openai.AsyncOpenAI(api_key="test-key", http_client=http_client, max_retries=0)


@pytest.fixture
def mock_adapter(mock_openai_client: openai.AsyncOpenAI) -> OpenAIAdapter:
    return OpenAIAdapter(make_settings(), client=mock_openai_client)


@pytest.fixture
async def client(mock_openai_client: openai.AsyncOpenAI) -> AsyncIterator[AsyncClient]:
    settings = make_settings()
    app = create_app(settings)
    async with LifespanManager(app):
        # Swap the lazily-built adapter for one wired to the mock transport.
        app.state.registry._adapters["openai"] = OpenAIAdapter(settings, client=mock_openai_client)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            yield http_client
