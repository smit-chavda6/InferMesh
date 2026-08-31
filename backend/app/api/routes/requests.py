"""``GET /v1/requests/{request_id}`` — fetch one stored request by id.

Phase 4: proves persisted requests are queryable by id (a DoD item). Admin auth
and the paginated Requests Explorer land in Phase 8.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequestLog
from app.db.session import get_session
from app.errors import GatewayError
from app.schemas.observability import StoredRequest

router = APIRouter(tags=["observability"])


class RequestNotFoundError(GatewayError):
    error_type = "request_not_found"
    status_code = 404


@router.get("/v1/requests/{request_id}", response_model=StoredRequest)
async def get_request(
    request_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RequestLog:
    row = (
        await session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
    ).scalar_one_or_none()
    if row is None:
        raise RequestNotFoundError(f"no request with id {request_id!r}")
    return row
