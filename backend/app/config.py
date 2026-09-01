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
ProviderName = Literal["openai", "anthropic", "gemini", "azure_foundry"]

# Canonical provider order. `azure_foundry` (Phase 11) is the Azure AI Model
# Inference API — distinct from the OpenAI adapter's `azure` mode, which targets
# the Azure *OpenAI* API on the same resource.
ALL_PROVIDERS: tuple[ProviderName, ...] = ("openai", "anthropic", "gemini", "azure_foundry")


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

    # --- Database ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://gateway:gateway@localhost:5432/gateway"
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    # One usage row is written per request when enabled. Disabling it keeps the
    # gateway working with no database (row-writing is best-effort regardless).
    usage_logging_enabled: bool = True

    # --- Metrics ------------------------------------------------------------
    # Prometheus exposition at GET /metrics. If METRICS_TOKEN is set, the
    # endpoint requires `Authorization: Bearer <token>`.
    metrics_enabled: bool = True
    metrics_token: str | None = None

    # --- Redis ---------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Dashboard admin auth ------------------------------------------
    jwt_secret: str = "dev-only-change-me"
    admin_email: str = "admin@example.com"
    admin_password: str = "admin"
    jwt_access_ttl_seconds: int = Field(default=900, ge=60)  # 15 min
    jwt_refresh_ttl_seconds: int = Field(default=604_800, ge=300)  # 7 days
    auth_cookie_secure: bool = True  # set false for local plain-HTTP dev
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)  # tests drop this to 4
    # Brute-force guard on POST /v1/auth/login, per client IP.
    admin_login_max_attempts: int = Field(default=10, ge=1)
    admin_login_window_seconds: int = Field(default=300, ge=1)

    # --- Request limits ---------------------------------------------------
    max_messages_per_request: int = Field(default=256, ge=1)
    max_prompt_chars: int = Field(default=600_000, ge=1)
    max_request_body_bytes: int = Field(default=5_000_000, ge=1024)

    # --- Client API keys / rate limiting --------------------------------
    # When true, /v1/chat/completions requires a valid `Authorization: Bearer`
    # gateway client key. When false, anonymous callers are allowed (dev/tests)
    # and rate-limited as one bucket.
    require_api_key: bool = False
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = Field(default=60, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_anon_per_minute: int = Field(default=120, ge=1)
    rate_limit_fail_open: bool = True  # if Redis is down, allow rather than 500

    # --- Caching ------------------------------------------------------
    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=300, ge=1)
    cache_namespace: str = "cache:chat"
    # Semantic cache: needs an embedding capability. Auto-disables if none is
    # configured (degrades to exact-match only, per spec §2.1).
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    semantic_cache_embedding_model: str = "text-embedding-3-small"
    # Azure only: the deployment name for the embedding model (if it exists).
    azure_openai_embedding_deployment: str | None = None

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

    # --- Azure AI Foundry (Phase 11) -------------------------------------------
    # The Azure AI Model Inference API exposed at
    # ``https://<resource>.services.ai.azure.com/models`` — one OpenAI-shaped REST
    # surface in front of every model deployed to a Foundry resource. Separate
    # from OPENAI_MODE=azure (Azure OpenAI): different path, different versioning,
    # its own deployments. ``azure_foundry_model`` is a deployment name.
    azure_foundry_endpoint: str | None = None
    azure_foundry_api_key: str | None = None
    azure_foundry_api_version: str = "2024-05-01-preview"
    azure_foundry_model: str = "gpt-4o-mini"
    azure_foundry_timeout_seconds: float = Field(default=60.0, gt=0)

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

    @property
    def azure_foundry_enabled(self) -> bool:
        return bool(self.azure_foundry_api_key and self.azure_foundry_endpoint)

    @property
    def semantic_cache_available(self) -> bool:
        """Semantic caching needs an OpenAI-family embedding capability."""
        if not (self.semantic_cache_enabled and self.openai_api_key):
            return False
        if self.openai_mode == "azure":
            return bool(self.azure_openai_embedding_deployment)
        return True

    def provider_enabled(self, name: str) -> bool:
        return {
            "openai": self.openai_enabled,
            "anthropic": self.anthropic_enabled,
            "gemini": self.gemini_enabled,
            "azure_foundry": self.azure_foundry_enabled,
        }.get(name, False)

    def available_providers(self) -> list[str]:
        return [p for p in ALL_PROVIDERS if self.provider_enabled(p)]

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        """Hard, fail-fast checks on malformed / unsafe configuration."""
        errors: list[str] = []

        if self.openai_mode == "azure" and self.openai_api_key and not self.azure_openai_endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is required when OPENAI_MODE=azure")

        if self.azure_foundry_api_key and not self.azure_foundry_endpoint:
            errors.append("AZURE_FOUNDRY_ENDPOINT is required when AZURE_FOUNDRY_API_KEY is set")

        if not self.database_url.startswith("postgresql+asyncpg://"):
            errors.append("DATABASE_URL must be a postgresql+asyncpg:// URL")
        if not self.redis_url.startswith(("redis://", "rediss://", "unix://")):
            errors.append("REDIS_URL must be a redis:// / rediss:// / unix:// URL")

        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            errors.append("RETRY_MAX_DELAY_SECONDS must be >= RETRY_BASE_DELAY_SECONDS")

        bad_provider = next((p for p in self.fallback_chain if p not in ALL_PROVIDERS), None)
        if bad_provider is not None:
            errors.append(f"FALLBACK_CHAIN contains unknown provider {bad_provider!r}")

        if self.environment == "production":
            if self.jwt_secret in ("", "dev-only-change-me", "change-me-to-a-long-random-string"):
                errors.append("JWT_SECRET must be set to a real secret in production")
            if len(self.jwt_secret) < 32:
                errors.append("JWT_SECRET must be at least 32 characters in production")
            if self.admin_password in ("", "admin", "change-me", "admin-dev-password"):
                errors.append("ADMIN_PASSWORD must be set to a real value in production")

        if errors:
            raise ValueError("invalid configuration: " + "; ".join(errors))
        return self

    def startup_warnings(self) -> list[str]:
        """Non-fatal issues worth logging loudly at startup (readiness gates traffic)."""
        warnings: list[str] = []
        if not self.available_providers():
            warnings.append(
                "no LLM providers are configured — /v1/chat/completions will return 503"
            )
        elif not self.fallback_enabled and self.default_provider not in self.available_providers():
            warnings.append(
                f"default provider '{self.default_provider}' is not configured and fallback is off"
            )
        if self.semantic_cache_enabled and not self.semantic_cache_available:
            warnings.append(
                "SEMANTIC_CACHE_ENABLED but no embedding key/deployment — exact-match cache only"
            )
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
