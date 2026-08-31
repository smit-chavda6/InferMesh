"""Common provider-adapter interface and normalized data types.

Every provider (OpenAI/Azure, Anthropic, Gemini) is wrapped behind
``ProviderAdapter``. No provider-specific request/response translation lives
outside an adapter module.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.schemas.chat import ChatCompletionRequest


@dataclass(slots=True)
class NormalizedUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class NormalizedCompletion:
    """Provider response translated back into the gateway's canonical shape."""

    id: str
    created: int
    model: str  # the upstream model / deployment that actually served the call
    role: str
    content: str | None
    finish_reason: str | None
    usage: NormalizedUsage
    tool_calls: list[dict[str, Any]] | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class StreamChunk:
    delta: str = ""
    finish_reason: str | None = None
    usage: NormalizedUsage | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class ProviderModel:
    id: str
    created: int | None = None
    owned_by: str | None = None


@dataclass(slots=True)
class HealthResult:
    healthy: bool
    latency_ms: float | None = None
    detail: str | None = None
    checked_models: list[str] = field(default_factory=list)


class ProviderAdapter(abc.ABC):
    """Interface implemented by every provider adapter."""

    name: str = "base"

    @abc.abstractmethod
    async def complete(self, request: ChatCompletionRequest) -> NormalizedCompletion:
        """Perform one non-streaming completion. Raises ``GatewayError`` subclasses on failure."""

    @abc.abstractmethod
    def stream(self, request: ChatCompletionRequest) -> AsyncIterator[StreamChunk]:
        """Return an async iterator of incremental chunks. (Implemented in Phase 5.)"""

    @abc.abstractmethod
    async def list_models(self) -> list[ProviderModel]:
        """List models/deployments visible to this provider's credentials."""

    @abc.abstractmethod
    async def health_check(self) -> HealthResult:
        """Cheap liveness probe against the provider."""

    async def aclose(self) -> None:
        """Release any held resources (HTTP clients). Safe to call more than once."""
        return None
