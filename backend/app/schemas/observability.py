"""Read models for stored observability data.

Phase 4 exposes a single stored request by id. Phase 8 builds the paginated
Requests Explorer and aggregation endpoints (§13, §27) on top of the same table.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class StoredRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    created_at: dt.datetime
    provider: str
    model: str
    upstream_model: str | None
    status: str
    http_status: int | None
    error_type: str | None
    error_message: str | None
    finish_reason: str | None

    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    cost_usd: Decimal | None
    input_cost_usd: Decimal | None
    output_cost_usd: Decimal | None
    pricing_version: str | None

    fallback_used: bool
    retries: int
    provider_chain: list[dict[str, Any]] | None

    cache_status: str
    cache_key: str | None
    streamed: bool
    message_count: int
    api_key_prefix: str | None
