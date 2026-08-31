from __future__ import annotations

import openai
import pytest

from app.errors import ProviderError, ProviderTimeoutError
from app.providers.openai_adapter import OpenAIAdapter
from app.schemas.chat import ChatCompletionRequest, ChatMessage


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "gpt-4o-mini",
        "messages": [ChatMessage(role="user", content="hi")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


async def test_complete_normalizes_response(mock_adapter: OpenAIAdapter) -> None:
    result = await mock_adapter.complete(_req())
    assert result.content == "Hello from the OpenAI mock."
    assert result.role == "assistant"
    assert result.finish_reason == "stop"
    assert result.model == "gpt-4o-mini-2024-07-18"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 18


async def test_forwarded_params_are_passed_through(mock_adapter: OpenAIAdapter) -> None:
    captured: dict[str, object] = {}
    original = mock_adapter._client.chat.completions.create

    async def spy(**kwargs: object):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return await original(**kwargs)

    mock_adapter._client.chat.completions.create = spy  # type: ignore[method-assign]
    await mock_adapter.complete(_req(temperature=0.2, max_tokens=64, stop=["\n"]))

    assert captured["temperature"] == 0.2
    # gateway accepts classic `max_tokens`; adapter speaks `max_completion_tokens`
    assert captured["max_completion_tokens"] == 64
    assert "max_tokens" not in captured
    assert captured["stop"] == ["\n"]
    assert "provider" not in captured
    assert "stream" not in captured


async def test_list_models(mock_adapter: OpenAIAdapter) -> None:
    models = await mock_adapter.list_models()
    assert {m.id for m in models} == {"gpt-4o-mini", "gpt-4o"}


async def test_health_check_ok(mock_adapter: OpenAIAdapter) -> None:
    health = await mock_adapter.health_check()
    assert health.healthy is True
    assert health.latency_ms is not None
    assert "gpt-4o-mini" in health.checked_models


async def test_errors_are_mapped_to_gateway_types(mock_adapter: OpenAIAdapter) -> None:
    async def raise_timeout(**_kwargs: object):  # type: ignore[no-untyped-def]
        raise openai.APITimeoutError(request=object())  # type: ignore[arg-type]

    mock_adapter._client.chat.completions.create = raise_timeout  # type: ignore[method-assign]
    with pytest.raises(ProviderTimeoutError):
        await mock_adapter.complete(_req())


async def test_generic_openai_error_is_wrapped(mock_adapter: OpenAIAdapter) -> None:
    async def raise_generic(**_kwargs: object):  # type: ignore[no-untyped-def]
        raise openai.APIConnectionError(message="boom", request=object())  # type: ignore[arg-type]

    mock_adapter._client.chat.completions.create = raise_generic  # type: ignore[method-assign]
    with pytest.raises(ProviderError):
        await mock_adapter.complete(_req())


async def test_stream_not_implemented(mock_adapter: OpenAIAdapter) -> None:
    with pytest.raises(NotImplementedError):
        async for _chunk in mock_adapter.stream(_req()):
            pass
