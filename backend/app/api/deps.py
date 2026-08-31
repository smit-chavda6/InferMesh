"""Request-scoped dependencies: resolving the calling project from its API key."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project
from app.db.session import get_session
from app.errors import InvalidAPIKeyError
from app.security import hash_api_key


@dataclass(slots=True)
class Caller:
    """Who is making the request + the rate-limit bucket to charge it against."""

    project: Project | None
    identifier: str  # rate-limit bucket key
    rate_limit_per_minute: int
    rate_limit_window_seconds: int
    api_key_prefix: str | None = None
    project_name: str | None = None


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


async def resolve_caller(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Caller:
    settings = request.app.state.settings
    token = _bearer_token(request)

    if token is not None:
        project = (
            await session.execute(select(Project).where(Project.key_hash == hash_api_key(token)))
        ).scalar_one_or_none()
        if project is None or project.status != "active":
            raise InvalidAPIKeyError("invalid or revoked API key")
        project.last_used_at = datetime.now(UTC)
        await session.commit()
        return Caller(
            project=project,
            identifier=f"key:{project.id}",
            rate_limit_per_minute=project.rate_limit_per_minute,
            rate_limit_window_seconds=project.rate_limit_window_seconds,
            api_key_prefix=project.key_prefix,
            project_name=project.name,
        )

    if settings.require_api_key:
        raise InvalidAPIKeyError("an API key is required (Authorization: Bearer ...)")

    client_ip = request.client.host if request.client else "unknown"
    return Caller(
        project=None,
        identifier=f"anon:{client_ip}",
        rate_limit_per_minute=settings.rate_limit_anon_per_minute,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
    )


CallerDep = Annotated[Caller, Depends(resolve_caller)]
