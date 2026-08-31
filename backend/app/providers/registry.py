"""Provider registry + minimal router.

Phase 1: build and cache adapters lazily, resolve a request to a single provider.
Phase 3 layers retry/backoff/fallback on top of this; Phase 2 registers the
Anthropic and Gemini adapters here.
"""

from __future__ import annotations

from app.config import Settings
from app.errors import ProviderNotConfiguredError
from app.logging_config import get_logger
from app.providers.base import ProviderAdapter
from app.providers.openai_adapter import OpenAIAdapter

log = get_logger(__name__)

_BUILDERS = {
    "openai": lambda settings: OpenAIAdapter(settings),
}


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._adapters: dict[str, ProviderAdapter] = {}

    def get(self, name: str) -> ProviderAdapter:
        if name not in self._adapters:
            builder = _BUILDERS.get(name)
            if builder is None:
                raise ProviderNotConfiguredError(name, "provider is not registered")
            self._adapters[name] = builder(self._settings)
            log.info("provider.registered", provider=name)
        return self._adapters[name]

    def resolve(self, requested: str | None) -> str:
        """Pick the provider name for a request (explicit field, else configured default)."""
        return requested or self._settings.default_provider

    def available(self) -> list[str]:
        return self._settings.available_providers()

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            try:
                await adapter.aclose()
            except Exception as exc:  # noqa: BLE001 — cleanup best-effort, but logged
                log.warning("provider.aclose_failed", provider=adapter.name, error=str(exc))
