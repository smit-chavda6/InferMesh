"""OpenAI-compatible chat completion request/response contract.

The gateway accepts an OpenAI-style body and returns an OpenAI-style body plus a
``gateway`` metadata object. Routing is driven by the optional ``provider`` field;
when omitted the configured default routing/fallback chain is used.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.gateway import GatewayMetadata

Role = Literal["system", "developer", "user", "assistant", "tool"]
ProviderName = Literal["openai", "anthropic", "gemini"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Role
    # ``content`` may be a plain string or the OpenAI content-part array.
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    # Lenient: unknown keys are ignored rather than rejected so OpenAI-compatible
    # clients keep working. Known optional fields below are forwarded to adapters.
    model_config = ConfigDict(extra="ignore")

    model: str = Field(min_length=1, max_length=256)
    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    provider: ProviderName | None = None

    stream: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0, le=200_000)
    n: int | None = Field(default=None, ge=1, le=10)
    stop: str | list[str] | None = None
    presence_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    frequency_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    seed: int | None = None
    user: str | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None

    def forwarded_params(self) -> dict[str, Any]:
        """Optional generation params to pass through to a provider adapter."""
        keys = (
            "temperature",
            "top_p",
            "max_tokens",
            "n",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "user",
            "response_format",
            "tools",
            "tool_choice",
        )
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


class ResponseMessage(BaseModel):
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ResponseChoice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ResponseChoice]
    usage: Usage
    gateway: GatewayMetadata
