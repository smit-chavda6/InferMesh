"""Phase 11 — Azure AI Foundry adapter.

The adapter talks raw REST, so every test drives it through an injected
``httpx.AsyncClient`` backed by a ``MockTransport`` handler: no network, full
control over status codes and bodies.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.errors import (
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.providers.azure_foundry_adapter import AzureFoundryAdapter, _inference_base
from app.schemas.chat import ChatCompletionRequest, ChatMessage

from .conftest import make_settings

_OK_BODY = {
    "id": "chatcmpl-foundry-1",
    "created": 1_760_000_000,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from Foundry."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
}


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [ChatMessage(role="user", content="hi")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


def _settings(**overrides: object) -> Settings:
    return make_settings(
        azure_foundry_endpoint="https://res.services.ai.azure.com",
        azure_foundry_api_key="fk-test",
        azure_foundry_model="gpt-4o-mini",
        **overrides,
    )


def _adapter(handler, **settings_overrides: object) -> AzureFoundryAdapter:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://res.services.ai.azure.com/models",
        headers={"api-key": "fk-test"},
    )
    return AzureFoundryAdapter(_settings(**settings_overrides), client=client)


# --- unit: endpoint normalisation ------------------------------------------


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("https://r.services.ai.azure.com", "https://r.services.ai.azure.com/models"),
        ("https://r.services.ai.azure.com/", "https://r.services.ai.azure.com/models"),
        ("https://r.services.ai.azure.com/models", "https://r.services.ai.azure.com/models"),
        ("https://r.services.ai.azure.com/models/", "https://r.services.ai.azure.com/models"),
    ],
)
def test_inference_base_is_idempotent(given: str, want: str) -> None:
    assert _inference_base(given) == want


# --- complete -------------------------------------------------------------


async def test_complete_builds_request_and_normalizes() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["path"] = request.url.path
        seen["api_version"] = request.url.params.get("api-version")
        seen["api_key"] = request.headers.get("api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_OK_BODY)

    adapter = _adapter(handler)
    result = await adapter.complete(_req(temperature=0.5, max_tokens=64))

    assert seen["path"] == "/models/chat/completions"
    assert seen["api_version"] == "2024-05-01-preview"
    assert seen["api_key"] == "fk-test"
    assert seen["body"]["model"] == "gpt-4o-mini"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert seen["body"]["temperature"] == 0.5
    # max_tokens is translated to the spelling current deployments require
    assert seen["body"]["max_completion_tokens"] == 64
    assert "max_tokens" not in seen["body"]
    assert "stream" not in seen["body"]

    assert result.id == "chatcmpl-foundry-1"
    assert result.content == "Hello from Foundry."
    assert result.role == "assistant"
    assert result.finish_reason == "stop"
    assert result.model == "gpt-4o-mini"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 4
    assert result.usage.total_tokens == 15


async def test_complete_falls_back_to_default_model_when_request_model_blank() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        return httpx.Response(200, json=_OK_BODY)

    adapter = _adapter(handler)
    # a fallback hop clears the provider-specific model (see routing._request_for)
    blank = _req().model_copy(update={"model": ""})
    await adapter.complete(blank)


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (400, ProviderBadRequestError),
        (404, ProviderBadRequestError),
        (500, ProviderError),
        (503, ProviderError),
    ],
)
async def test_complete_maps_http_errors(status: int, exc: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": f"boom {status}"}})

    adapter = _adapter(handler)
    with pytest.raises(exc) as ei:
        await adapter.complete(_req())
    assert "azure_foundry" in str(ei.value)


async def test_complete_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    adapter = _adapter(handler)
    with pytest.raises(ProviderTimeoutError):
        await adapter.complete(_req())


async def test_complete_maps_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    adapter = _adapter(handler)
    with pytest.raises(ProviderError):
        await adapter.complete(_req())


# --- stream -------------------------------------------------------------


async def test_stream_parses_sse_and_accumulates_usage() -> None:
    chunks = [
        'data: {"id":"c1","model":"gpt-4o-mini","choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"id":"c1","choices":[{"delta":{"content":"lo"}}]}',
        'data: {"id":"c1","choices":[{"delta":{},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}',
        "data: [DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text="\n\n".join(chunks))

    adapter = _adapter(handler)
    out = [c async for c in adapter.stream(_req())]

    assert "".join(c.delta for c in out) == "Hello"
    assert out[-1].finish_reason == "stop"
    assert out[-1].usage is not None
    assert out[-1].usage.total_tokens == 5


async def test_stream_maps_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    adapter = _adapter(handler)
    with pytest.raises(ProviderRateLimitError):
        _ = [c async for c in adapter.stream(_req())]


# --- health / models --------------------------------------------------


async def test_health_check_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["max_completion_tokens"] == 16
        return httpx.Response(200, json=_OK_BODY)

    adapter = _adapter(handler)
    h = await adapter.health_check()
    assert h.healthy is True
    assert h.latency_ms is not None
    assert h.checked_models == ["gpt-4o-mini"]


async def test_health_check_reports_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    adapter = _adapter(handler)
    h = await adapter.health_check()
    assert h.healthy is False
    assert h.detail


async def test_list_models_returns_configured_deployment() -> None:
    adapter = _adapter(lambda r: httpx.Response(200, json=_OK_BODY))
    models = await adapter.list_models()
    assert [m.id for m in models] == ["gpt-4o-mini"]
    assert models[0].owned_by == "azure_foundry"


# --- config / registry wiring --------------------------------------------


def test_provider_is_registered_and_gated_by_config() -> None:
    from app.providers.registry import ProviderRegistry

    off = make_settings()
    assert off.azure_foundry_enabled is False
    assert "azure_foundry" not in off.available_providers()

    on = _settings()
    assert on.azure_foundry_enabled is True
    assert "azure_foundry" in on.available_providers()
    assert isinstance(ProviderRegistry(on).get("azure_foundry"), AzureFoundryAdapter)


def test_endpoint_required_when_key_set() -> None:
    with pytest.raises(ValueError, match="AZURE_FOUNDRY_ENDPOINT"):
        make_settings(azure_foundry_api_key="fk-test", azure_foundry_endpoint=None)


def test_unknown_provider_in_fallback_chain_still_rejected() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        make_settings(fallback_chain=["openai", "not-a-provider"])

    # but azure_foundry is now accepted
    s = make_settings(fallback_chain=["openai", "azure_foundry"])
    assert s.fallback_chain == ["openai", "azure_foundry"]
