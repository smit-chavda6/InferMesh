"""Response caching: exact-match (Redis) with an optional semantic layer (pgvector).

Lookup order on a request: exact-match hash in Redis, then — only if an embedding
capability is configured — nearest-neighbour search in Postgres. If no embedding
key is set, semantic caching is silently skipped and the gateway runs
exact-match only (spec §2.1).

Only non-streaming requests are cached.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import openai
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import EMBEDDING_DIM, SemanticCacheEntry
from app.logging_config import get_logger
from app.pricing import PricingTable
from app.providers._common import text_of
from app.schemas.chat import ChatCompletionRequest

log = get_logger(__name__)

_HASH_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "n",
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "response_format",
    "tools",
    "tool_choice",
)


@dataclass(slots=True)
class CachedResponse:
    id: str
    created: int
    provider: str
    model: str  # upstream model
    role: str
    content: str | None
    finish_reason: str | None
    usage: dict[str, int]
    tool_calls: list[dict[str, Any]] | None = None
    cost_usd: float | None = None
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    pricing_version: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> CachedResponse:
        return cls(**json.loads(raw))


@dataclass(slots=True)
class CacheLookup:
    hit: bool
    kind: str = "MISS"  # "EXACT" | "SEMANTIC" | "MISS"
    key: str | None = None
    response: CachedResponse | None = None


def exact_key(request: ChatCompletionRequest) -> str:
    payload: dict[str, Any] = {
        "provider": request.provider or "auto",
        "model": request.model,
        "messages": [
            {"role": m.role, "content": m.content, "name": m.name} for m in request.messages
        ],
    }
    for f in _HASH_FIELDS:
        val = getattr(request, f, None)
        if val is not None:
            payload[f] = val
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def prompt_text(request: ChatCompletionRequest) -> str:
    return "\n".join(f"{m.role}: {text_of(m.content)}" for m in request.messages)


def prompt_hash(request: ChatCompletionRequest) -> str:
    return hashlib.sha256(prompt_text(request).encode()).hexdigest()


class Embedder:
    """Thin wrapper over OpenAI/Azure embeddings. ``available`` is False when no
    key/deployment is configured (semantic caching then degrades to exact-only)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.available = settings.semantic_cache_available
        self._client: openai.AsyncOpenAI | None = None
        if not self.available:
            return
        if settings.openai_mode == "azure":
            self._client = openai.AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint or "",
                api_version=settings.azure_openai_api_version,
                api_key=settings.openai_api_key or "",
                max_retries=1,
            )
            self._model = settings.azure_openai_embedding_deployment or ""
        else:
            kwargs: dict[str, Any] = {"api_key": settings.openai_api_key, "max_retries": 1}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = openai.AsyncOpenAI(**kwargs)
            self._model = settings.semantic_cache_embedding_model

    async def embed(self, text_in: str) -> list[float] | None:
        if not self.available or self._client is None:
            return None
        try:
            resp = await self._client.embeddings.create(model=self._model, input=text_in)
            return list(resp.data[0].embedding)
        except Exception as exc:  # noqa: BLE001 - semantic cache is best-effort
            log.warning("cache.embed_failed", error=str(exc))
            return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()


class ChatCache:
    def __init__(
        self,
        redis_client: Any,
        sessionmaker: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        settings: Settings,
        pricing: PricingTable,
    ) -> None:
        self._redis = redis_client
        self._sessionmaker = sessionmaker
        self._embedder = embedder
        self._settings = settings
        self._pricing = pricing
        self._ns = settings.cache_namespace

    @property
    def semantic_enabled(self) -> bool:
        return self._settings.semantic_cache_enabled and self._embedder.available

    # -- lookup ----------------------------------------------------------

    async def lookup(self, request: ChatCompletionRequest) -> CacheLookup:
        if not self._settings.cache_enabled or request.stream:
            return CacheLookup(hit=False)

        key = exact_key(request)
        try:
            raw = await self._redis.get(f"{self._ns}:{key}")
        except Exception as exc:  # noqa: BLE001 - cache miss on Redis error
            log.warning("cache.redis_get_failed", error=str(exc))
            raw = None
        if raw:
            return CacheLookup(
                hit=True, kind="EXACT", key=key, response=CachedResponse.from_json(raw)
            )

        if self.semantic_enabled:
            sem = await self._semantic_lookup(request)
            if sem is not None:
                return CacheLookup(hit=True, kind="SEMANTIC", key=key, response=sem)

        return CacheLookup(hit=False, key=key)

    async def _semantic_lookup(self, request: ChatCompletionRequest) -> CachedResponse | None:
        vec = await self._embedder.embed(prompt_text(request))
        if vec is None or len(vec) != EMBEDDING_DIM:
            return None
        provider = request.provider or "auto"
        threshold = self._settings.semantic_cache_threshold
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(
                        SemanticCacheEntry,
                        (1 - SemanticCacheEntry.embedding.cosine_distance(vec)).label("sim"),
                    )
                    .where(SemanticCacheEntry.model == request.model)
                    .where(
                        SemanticCacheEntry.provider.in_([provider, request.provider or provider])
                    )
                    .where(
                        (SemanticCacheEntry.expires_at.is_(None))
                        | (SemanticCacheEntry.expires_at > datetime.now(UTC))
                    )
                    .order_by(SemanticCacheEntry.embedding.cosine_distance(vec))
                    .limit(1)
                )
            ).first()
            if row is None:
                return None
            entry, sim = row
            if sim is None or float(sim) < threshold:
                return None
            entry.hits += 1
            entry.last_hit_at = datetime.now(UTC)
            await session.commit()
            log.info("cache.semantic_hit", similarity=round(float(sim), 4), model=request.model)
            return CachedResponse(**entry.response)

    # -- store -------------------------------------------------------

    async def store(
        self, request: ChatCompletionRequest, key: str | None, response: CachedResponse
    ) -> None:
        if not self._settings.cache_enabled or request.stream:
            return
        key = key or exact_key(request)
        try:
            await self._redis.set(
                f"{self._ns}:{key}", response.to_json(), ex=self._settings.cache_ttl_seconds
            )
        except Exception as exc:  # noqa: BLE001 - non-fatal
            log.warning("cache.redis_set_failed", error=str(exc))

        if self.semantic_enabled:
            await self._semantic_store(request, response)

    async def _semantic_store(
        self, request: ChatCompletionRequest, response: CachedResponse
    ) -> None:
        vec = await self._embedder.embed(prompt_text(request))
        if vec is None or len(vec) != EMBEDDING_DIM:
            return
        ph = prompt_hash(request)
        expires = datetime.now(UTC) + timedelta(seconds=self._settings.cache_ttl_seconds)
        async with self._sessionmaker() as session:
            exists = await session.scalar(
                select(SemanticCacheEntry.id)
                .where(SemanticCacheEntry.prompt_hash == ph)
                .where(SemanticCacheEntry.model == request.model)
                .limit(1)
            )
            if exists:
                return
            session.add(
                SemanticCacheEntry(
                    embedding=vec,
                    provider=request.provider or "auto",
                    model=request.model,
                    prompt_hash=ph,
                    response=asdict(response),
                    cost_usd=Decimal(str(response.cost_usd)) if response.cost_usd else None,
                    prompt_tokens=response.usage.get("prompt_tokens", 0),
                    completion_tokens=response.usage.get("completion_tokens", 0),
                    expires_at=expires,
                )
            )
            await session.commit()

    async def stats(self) -> dict[str, Any]:
        """Best-effort snapshot for /v1/cache/stats (fleshed out in Phase 8)."""
        info: dict[str, Any] = {"namespace": self._ns, "semantic_enabled": self.semantic_enabled}
        try:
            keys = await self._redis.keys(f"{self._ns}:*")
            info["exact_entries"] = len(keys)
        except Exception as exc:  # noqa: BLE001
            log.warning("cache.stats_failed", error=str(exc))
            info["exact_entries"] = None
        if self.semantic_enabled:
            async with self._sessionmaker() as session:
                info["semantic_entries"] = await session.scalar(
                    text("SELECT count(*) FROM semantic_cache")
                )
        return info
