"""Application configuration.

Settings load from environment variables (and an optional ``.env`` file). Phase 1
keeps validation light; Phase 7 hardens startup validation for every dependency.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]
ProviderName = Literal["openai", "anthropic", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "LLM Gateway"
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True

    # --- Routing defaults ---
    default_provider: ProviderName = "openai"

    # --- OpenAI / Azure OpenAI --------------------------------------------------
    # A single adapter serves native OpenAI and Azure OpenAI; ``openai_mode``
    # selects which client is constructed. This keeps Azure out of a separate
    # Phase 11 adapter while still working with an Azure-only key.
    openai_mode: Literal["native", "azure"] = "native"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_default_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)

    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None

    # --- Anthropic -----------------------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    anthropic_default_model: str = "claude-3-5-sonnet-latest"
    anthropic_timeout_seconds: float = Field(default=60.0, gt=0)
    # Anthropic's API requires max_tokens; used when a request doesn't set one.
    anthropic_default_max_tokens: int = Field(default=1024, gt=0)

    # --- Gemini ------------------------------------------------------------
    gemini_api_key: str | None = None
    gemini_default_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = Field(default=60.0, gt=0)

    # --- Reliability: retry / backoff / fallback ---------------------------
    # Total attempts per provider before giving up on it (1 initial + N-1 retries).
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=0.5, ge=0)
    retry_max_delay_seconds: float = Field(default=8.0, ge=0)
    retry_backoff_multiplier: float = Field(default=2.0, ge=1.0)
    retry_jitter: bool = True
    # Hard ceiling on a single provider attempt (backstop for a hung SDK call).
    provider_attempt_timeout_seconds: float = Field(default=90.0, gt=0)
    # When a request names no provider, try this ordered chain (filtered to
    # enabled providers). JSON list in env, e.g. FALLBACK_CHAIN='["openai","gemini"]'.
    fallback_enabled: bool = True
    fallback_chain: list[str] = Field(default_factory=lambda: ["openai", "anthropic", "gemini"])
    # If a request DOES name a provider and it fails, still fall through to the
    # rest of the chain (vs. failing hard on the named provider only).
    fallback_on_explicit_provider: bool = True

    @property
    def openai_enabled(self) -> bool:
        if not self.openai_api_key:
            return False
        if self.openai_mode == "azure":
            return bool(self.azure_openai_endpoint)
        return True

    @property
    def anthropic_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    def provider_enabled(self, name: str) -> bool:
        return {
            "openai": self.openai_enabled,
            "anthropic": self.anthropic_enabled,
            "gemini": self.gemini_enabled,
        }.get(name, False)

    def available_providers(self) -> list[str]:
        return [p for p in ("openai", "anthropic", "gemini") if self.provider_enabled(p)]

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        errors: list[str] = []
        if self.openai_mode == "azure" and self.openai_api_key and not self.azure_openai_endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is required when OPENAI_MODE=azure")
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
