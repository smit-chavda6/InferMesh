"""Liveness endpoint.

Deliberately shallow — it does not probe Postgres/Redis/providers. The deep
dependency health surface arrives with ``/v1/system/health`` in Phase 8/20.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
        "providers_available": request.app.state.registry.available(),
    }
