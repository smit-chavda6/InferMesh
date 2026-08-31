"""Shared test fixtures.

The OpenAI and Anthropic SDKs (v3.x / v1.x) talk over ``httpx2``, so those are
mocked at the transport layer with ``httpx2.MockTransport`` — exercising the
adapters' real request-building and response-parsing. The google-genai client is
mocked at the SDK method boundary (it has a more involved transport stack), so
its translation code still runs against a constructed response object.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import anthropic
import httpx2
import openai
import pytest
from asgi_lifespan import LifespanManager
from google import genai
from google.genai import types as genai_types
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("LOG_JSON", "false")

from app.config import Settings
from app.main import create_app
from app.providers.anthropic_adapter import AnthropicAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.openai_adapter import OpenAIAdapter


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "log_json": False,
        "openai_api_key": "test-openai-key",
        "openai_mode": "native",
        "anthropic_api_key": "test-anthropic-key",
        "gemini_api_key": "test-gemini-key",
        "default_provider": "openai",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


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


def _openai_handler(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/chat/completions"):
        return httpx2.Response(200, json=CHAT_COMPLETION_FIXTURE)
    if path.endswith("/models"):
        return httpx2.Response(200, json=OPENAI_MODELS_FIXTURE)
    return httpx2.Response(404, json={"error": {"message": f"unmocked path {path}"}})


@pytest.fixture
def mock_openai_client() -> openai.AsyncOpenAI:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(_openai_handler))
    return openai.AsyncOpenAI(api_key="test-key", http_client=http_client, max_retries=0)


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


def _anthropic_handler(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/v1/messages"):
        return httpx2.Response(200, json=ANTHROPIC_MESSAGE_FIXTURE)
    if path.endswith("/v1/models"):
        return httpx2.Response(200, json=ANTHROPIC_MODELS_FIXTURE)
    return httpx2.Response(404, json={"type": "error", "error": {"message": f"unmocked {path}"}})


@pytest.fixture
def mock_anthropic_client() -> anthropic.AsyncAnthropic:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(_anthropic_handler))
    return anthropic.AsyncAnthropic(api_key="test-key", http_client=http_client, max_retries=0)


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


def make_gemini_adapter(
    response: genai_types.GenerateContentResponse | None = None,
    error: Exception | None = None,
) -> GeminiAdapter:
    adapter = GeminiAdapter(make_settings(), client=genai.Client(api_key="test-key"))

    async def fake_generate_content(**_kwargs: object) -> genai_types.GenerateContentResponse:
        if error is not None:
            raise error
        return response or GEMINI_RESPONSE

    adapter._client.aio.models.generate_content = fake_generate_content  # type: ignore[method-assign]
    return adapter


@pytest.fixture
def mock_gemini_adapter() -> GeminiAdapter:
    return make_gemini_adapter()


# --- Full gateway (all three providers mocked) --------------------------


@pytest.fixture
async def client(
    mock_openai_client: openai.AsyncOpenAI,
    mock_anthropic_client: anthropic.AsyncAnthropic,
) -> AsyncIterator[AsyncClient]:
    settings = make_settings()
    app = create_app(settings)
    async with LifespanManager(app):
        registry = app.state.registry
        registry._adapters["openai"] = OpenAIAdapter(settings, client=mock_openai_client)
        registry._adapters["anthropic"] = AnthropicAdapter(settings, client=mock_anthropic_client)
        registry._adapters["gemini"] = make_gemini_adapter()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as http_client:
            yield http_client
