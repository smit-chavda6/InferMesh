from __future__ import annotations

import anthropic
import httpx2
import pytest

from app.errors import ProviderBadRequestError, ProviderError
from app.providers.anthropic_adapter import AnthropicAdapter
from app.schemas.chat import ChatCompletionRequest, ChatMessage


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "claude-3-5-sonnet-latest",
        "messages": [ChatMessage(role="user", content="hi")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


async def test_complete_normalizes_response(mock_anthropic_adapter: AnthropicAdapter) -> None:
    result = await mock_anthropic_adapter.complete(_req())
    assert result.content == "Hello from the Anthropic mock."
    assert result.role == "assistant"
    assert result.finish_reason == "stop"  # end_turn -> stop
    assert result.usage.prompt_tokens == 13
    assert result.usage.completion_tokens == 9
    assert result.usage.total_tokens == 22


async def test_system_prompt_is_hoisted_and_max_tokens_defaulted(
    mock_anthropic_adapter: AnthropicAdapter,
) -> None:
    captured: dict[str, object] = {}
    original = mock_anthropic_adapter._client.messages.create

    async def spy(**kwargs: object):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return await original(**kwargs)

    mock_anthropic_adapter._client.messages.create = spy  # type: ignore[method-assign]
    await mock_anthropic_adapter.complete(
        _req(
            messages=[
                ChatMessage(role="system", content="Be terse."),
                ChatMessage(role="user", content="hi"),
            ]
        )
    )

    assert captured["system"] == "Be terse."
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["max_tokens"] == 1024  # anthropic_default_max_tokens


async def test_request_max_tokens_is_respected(mock_anthropic_adapter: AnthropicAdapter) -> None:
    captured: dict[str, object] = {}
    original = mock_anthropic_adapter._client.messages.create

    async def spy(**kwargs: object):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return await original(**kwargs)

    mock_anthropic_adapter._client.messages.create = spy  # type: ignore[method-assign]
    await mock_anthropic_adapter.complete(_req(max_tokens=256, stop="END"))
    assert captured["max_tokens"] == 256
    assert captured["stop_sequences"] == ["END"]


async def test_list_models(mock_anthropic_adapter: AnthropicAdapter) -> None:
    models = await mock_anthropic_adapter.list_models()
    assert [m.id for m in models] == ["claude-3-5-sonnet-20241022"]


async def test_health_check_ok(mock_anthropic_adapter: AnthropicAdapter) -> None:
    health = await mock_anthropic_adapter.health_check()
    assert health.healthy is True
    assert health.latency_ms is not None


async def test_errors_are_mapped(mock_anthropic_adapter: AnthropicAdapter) -> None:
    response = httpx2.Response(
        400,
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"),
        json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}},
    )

    async def raise_bad_request(**_kwargs: object):  # type: ignore[no-untyped-def]
        raise anthropic.BadRequestError(message="bad", response=response, body=None)

    mock_anthropic_adapter._client.messages.create = raise_bad_request  # type: ignore[method-assign]
    with pytest.raises(ProviderBadRequestError):
        await mock_anthropic_adapter.complete(_req())


async def test_generic_error_is_wrapped(mock_anthropic_adapter: AnthropicAdapter) -> None:
    async def raise_conn(**_kwargs: object):  # type: ignore[no-untyped-def]
        raise anthropic.APIConnectionError(message="boom", request=object())  # type: ignore[arg-type]

    mock_anthropic_adapter._client.messages.create = raise_conn  # type: ignore[method-assign]
    with pytest.raises(ProviderError):
        await mock_anthropic_adapter.complete(_req())


async def test_stream_not_implemented(mock_anthropic_adapter: AnthropicAdapter) -> None:
    with pytest.raises(NotImplementedError):
        async for _chunk in mock_anthropic_adapter.stream(_req()):
            pass
