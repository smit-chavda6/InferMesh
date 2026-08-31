from __future__ import annotations

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.errors import ProviderBadRequestError, ProviderError, ProviderRateLimitError
from app.providers.gemini_adapter import GeminiAdapter
from app.schemas.chat import ChatCompletionRequest, ChatMessage

from .conftest import make_gemini_adapter


def _req(**overrides: object) -> ChatCompletionRequest:
    payload: dict[str, object] = {
        "model": "gemini-3.6-flash",
        "messages": [ChatMessage(role="user", content="hi")],
    }
    payload.update(overrides)
    return ChatCompletionRequest(**payload)  # type: ignore[arg-type]


async def test_complete_normalizes_response(mock_gemini_adapter: GeminiAdapter) -> None:
    result = await mock_gemini_adapter.complete(_req())
    assert result.content == "Hello from the Gemini mock."
    assert result.role == "assistant"
    assert result.finish_reason == "stop"  # STOP -> stop
    assert result.model == "gemini-3.6-flash"
    assert result.usage.prompt_tokens == 6
    # completion = total - prompt = 15 - 6 (covers visible + thinking tokens)
    assert result.usage.completion_tokens == 9
    assert result.usage.total_tokens == 15


async def test_system_and_params_are_translated() -> None:
    captured: dict[str, object] = {}
    adapter = make_gemini_adapter()

    async def spy(**kwargs: object) -> genai_types.GenerateContentResponse:
        captured.update(kwargs)
        from .conftest import GEMINI_RESPONSE

        return GEMINI_RESPONSE

    adapter._client.aio.models.generate_content = spy  # type: ignore[method-assign]

    await adapter.complete(
        _req(
            messages=[
                ChatMessage(role="system", content="Be terse."),
                ChatMessage(role="user", content="hello"),
                ChatMessage(role="assistant", content="hi"),
                ChatMessage(role="user", content="again"),
            ],
            temperature=0.3,
            max_tokens=128,
            stop="END",
        )
    )

    assert captured["model"] == "gemini-3.6-flash"
    contents = captured["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]  # assistant -> model
    assert contents[0].parts[0].text == "hello"

    config = captured["config"]
    assert config.system_instruction == "Be terse."
    assert config.temperature == 0.3
    assert config.max_output_tokens == 128
    assert config.stop_sequences == ["END"]
    assert config.automatic_function_calling.disable is True


async def test_blocked_response_yields_none_content_not_error() -> None:
    blocked = genai_types.GenerateContentResponse.model_validate(
        {
            "candidates": [{"finish_reason": "SAFETY"}],
            "usage_metadata": {"prompt_token_count": 4, "total_token_count": 4},
            "response_id": "resp-blocked",
        }
    )
    adapter = make_gemini_adapter(response=blocked)
    result = await adapter.complete(_req())
    assert result.content is None
    assert result.finish_reason == "content_filter"
    assert result.usage.completion_tokens == 0


async def test_client_error_maps_to_rate_limit() -> None:
    err = genai_errors.ClientError(429, {"error": {"message": "quota", "code": 429}})
    adapter = make_gemini_adapter(error=err)
    with pytest.raises(ProviderRateLimitError):
        await adapter.complete(_req())


async def test_client_error_400_maps_to_bad_request() -> None:
    err = genai_errors.ClientError(400, {"error": {"message": "bad", "code": 400}})
    adapter = make_gemini_adapter(error=err)
    with pytest.raises(ProviderBadRequestError):
        await adapter.complete(_req())


async def test_unexpected_error_is_wrapped_not_swallowed() -> None:
    adapter = make_gemini_adapter(error=RuntimeError("kaboom"))
    with pytest.raises(ProviderError):
        await adapter.complete(_req())


async def test_stream_not_implemented(mock_gemini_adapter: GeminiAdapter) -> None:
    with pytest.raises(NotImplementedError):
        async for _chunk in mock_gemini_adapter.stream(_req()):
            pass
