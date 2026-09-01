"""Requests Explorer (spec §13, §14): paginated list + single-request detail.
Both require an admin session.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.dashboard import queries as q
from app.dashboard.timerange import resolve_range
from app.db.models import RequestLog
from app.db.session import get_session
from app.errors import GatewayError
from app.schemas.observability import StoredRequest

router = APIRouter(
    prefix="/v1/requests", tags=["observability"], dependencies=[Depends(require_admin)]
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_MAX_PAGE_SIZE = 200  # enforced server-side even if the client asks for more (§13)
_EXPORT_CAP = 50_000  # hard ceiling on a CSV export

_CSV_COLUMNS = (
    "request_id",
    "created_at",
    "provider",
    "model",
    "upstream_model",
    "status",
    "http_status",
    "error_type",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "cache_status",
    "fallback_used",
    "retries",
    "streamed",
    "project_name",
    "api_key_prefix",
    "finish_reason",
)


class RequestNotFoundError(GatewayError):
    error_type = "request_not_found"
    status_code = 404


class BadRangeError(GatewayError):
    error_type = "bad_range"
    status_code = 400


@router.get("")
async def list_requests(
    session: SessionDep,
    range: Annotated[str, Query(pattern="^(1h|24h|7d|30d|custom)$")] = "24h",
    frm: Annotated[dt.datetime | None, Query(alias="from")] = None,
    to: dt.datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 50,
    sort: str = "created_at",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    provider: str | None = None,
    model: str | None = None,
    status: Annotated[str | None, Query(pattern="^(success|error)$")] = None,
    project_id: str | None = None,
    fallback_only: bool = False,
    cache_hit_only: bool = False,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> dict[str, Any]:
    try:
        tr = resolve_range(range, frm, to)
    except ValueError as exc:
        raise BadRangeError(str(exc)) from exc

    page_size = min(page_size, _MAX_PAGE_SIZE)
    items, total = await q.requests_page(
        session,
        tr,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        provider=provider,
        model=model,
        status=status,
        project_id=project_id,
        fallback_only=fallback_only,
        cache_hit_only=cache_hit_only,
        search=search,
    )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": page * page_size < total,
    }


@router.get("/export.csv")
async def export_requests_csv(
    session: SessionDep,
    range: Annotated[str, Query(pattern="^(1h|24h|7d|30d|custom)$")] = "24h",
    frm: Annotated[dt.datetime | None, Query(alias="from")] = None,
    to: dt.datetime | None = None,
    sort: str = "created_at",
    direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    provider: str | None = None,
    model: str | None = None,
    status: Annotated[str | None, Query(pattern="^(success|error)$")] = None,
    project_id: str | None = None,
    fallback_only: bool = False,
    cache_hit_only: bool = False,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> StreamingResponse:
    """Every row matching the current filters, as CSV (capped at 50k rows)."""
    try:
        tr = resolve_range(range, frm, to)
    except ValueError as exc:
        raise BadRangeError(str(exc)) from exc

    items, _ = await q.requests_page(
        session,
        tr,
        page=1,
        page_size=_EXPORT_CAP,
        sort=sort,
        direction=direction,
        provider=provider,
        model=model,
        status=status,
        project_id=project_id,
        fallback_only=fallback_only,
        cache_hit_only=cache_hit_only,
        search=search,
    )

    async def rows() -> AsyncIterator[str]:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(_CSV_COLUMNS)
        for it in items:
            writer.writerow([_csv_cell(it.get(c)) for c in _CSV_COLUMNS])
            if buf.tell() > 32_000:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
        if buf.tell():
            yield buf.getvalue()

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="requests-{stamp}.csv"'},
    )


def _csv_cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.isoformat()
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


@router.get("/{request_id}", response_model=StoredRequest)
async def get_request(request_id: str, session: SessionDep) -> RequestLog:
    row = (
        await session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
    ).scalar_one_or_none()
    if row is None:
        raise RequestNotFoundError(f"no request with id {request_id!r}")
    return row
