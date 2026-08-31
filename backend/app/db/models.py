"""SQLAlchemy models.

Phase 4 introduces a single table — ``requests`` — which is the observability
source of truth: one row per gateway request, carrying the request metadata,
token usage, cost breakdown, the fallback/retry chain, and cache status. The
dashboard's Requests Explorer (§13) maps almost 1:1 onto these columns.

Projects / API keys / alerts get their own tables in later phases; until then
``api_key_prefix`` is a plain nullable string.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EMBEDDING_DIM = 1536  # text-embedding-3-small


class RequestLog(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Public gateway request id ("req_<hex>"); the lookup key for /v1/requests/{id}.
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # --- routing outcome ---
    provider: Mapped[str] = mapped_column(String(32), index=True)  # provider actually used
    model: Mapped[str] = mapped_column(String(128), index=True)  # model as requested
    upstream_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(16), index=True)  # "success" | "error"
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- latency / usage ---
    latency_ms: Mapped[float] = mapped_column(Float)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # --- cost (nullable when the pricing table has no entry) ---
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True, index=True)
    input_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    output_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- reliability ---
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    provider_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # --- cache ---
    cache_status: Mapped[str] = mapped_column(String(16), default="DISABLED", index=True)
    cache_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # On a HIT, cost_usd is 0 and this holds what the call would have cost.
    cache_saved_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # --- caller ---
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_key_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # --- misc ---
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<RequestLog {self.request_id} {self.provider}/{self.model} {self.status}>"


class Project(Base):
    """A client 'project' — one gateway API key, its rate limit, and usage rollups.

    Full CRUD (create/rotate/revoke) + the admin dashboard land in Phase 8; Phase 6
    needs the row to identify a caller and look up their per-key rate limit.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex
    key_prefix: Mapped[str] = mapped_column(String(20))  # e.g. "sk-gw-7f92"
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|revoked

    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=60)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.name} {self.key_prefix} {self.status}>"


class SemanticCacheEntry(Base):
    """A cached completion keyed by prompt embedding (cosine similarity search)."""

    __tablename__ = "semantic_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)  # exact-dup guard
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_hit_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
