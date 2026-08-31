"""Project / API-key management (spec §19, §27).

The full key value is returned exactly once — at creation and on rotate — and
never stored in plaintext or retrievable again (only its SHA-256 hash + a short
prefix are persisted).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db.models import Project
from app.db.session import get_session
from app.errors import NotFoundError
from app.security import generate_api_key, hash_api_key, key_display_prefix

router = APIRouter(prefix="/v1/projects", tags=["projects"], dependencies=[Depends(require_admin)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)


class ProjectOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    status: str
    rate_limit_per_minute: int
    rate_limit_window_seconds: int
    created_at: datetime
    last_used_at: datetime | None


class CreatedProject(ProjectOut):
    api_key: str  # shown once


async def _get(session: AsyncSession, project_id: str) -> Project:
    try:
        pid = uuid.UUID(project_id)
    except ValueError as exc:
        raise NotFoundError(f"no project {project_id!r}") from exc
    row = (await session.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"no project {project_id!r}")
    return row


def _out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=str(p.id),
        name=p.name,
        key_prefix=p.key_prefix,
        status=p.status,
        rate_limit_per_minute=p.rate_limit_per_minute,
        rate_limit_window_seconds=p.rate_limit_window_seconds,
        created_at=p.created_at,
        last_used_at=p.last_used_at,
    )


@router.post("", response_model=CreatedProject, status_code=201)
async def create_project(body: CreateProjectBody, session: SessionDep) -> CreatedProject:
    key = generate_api_key()
    project = Project(
        name=body.name,
        key_hash=hash_api_key(key),
        key_prefix=key_display_prefix(key),
        rate_limit_per_minute=body.rate_limit_per_minute,
        rate_limit_window_seconds=body.rate_limit_window_seconds,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return CreatedProject(**_out(project).model_dump(), api_key=key)


@router.post("/{project_id}/rotate", response_model=CreatedProject)
async def rotate_key(project_id: str, session: SessionDep) -> CreatedProject:
    project = await _get(session, project_id)
    key = generate_api_key()
    project.key_hash = hash_api_key(key)
    project.key_prefix = key_display_prefix(key)
    await session.commit()
    await session.refresh(project)
    return CreatedProject(**_out(project).model_dump(), api_key=key)


@router.post("/{project_id}/revoke", response_model=ProjectOut)
async def revoke_project(project_id: str, session: SessionDep) -> ProjectOut:
    project = await _get(session, project_id)
    project.status = "revoked"
    project.last_used_at = project.last_used_at or datetime.now(UTC)
    await session.commit()
    await session.refresh(project)
    return _out(project)
