"""Requests Explorer (spec §13, §14): paginated list + single-request detail.
Both require an admin session.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
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


@router.get("/{request_id}", response_model=StoredRequest)
async def get_request(request_id: str, session: SessionDep) -> RequestLog:
    row = (
        await session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
    ).scalar_one_or_none()
    if row is None:
        raise RequestNotFoundError(f"no request with id {request_id!r}")
    return row
