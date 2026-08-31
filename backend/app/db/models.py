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
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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

    # --- cache (populated from Phase 6) ---
    cache_status: Mapped[str] = mapped_column(String(16), default="DISABLED", index=True)
    cache_key: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # --- misc ---
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    api_key_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<RequestLog {self.request_id} {self.provider}/{self.model} {self.status}>"
