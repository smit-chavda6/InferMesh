"""Liveness (`/health`) and readiness (`/health/ready`) endpoints.

`/health` is a shallow "the process is up" probe — it must never touch Postgres,
Redis or providers, so a container orchestrator won't kill a pod during a
transient dependency blip.

`/health/ready` probes the hard dependencies (Postgres, Redis) plus whether any
LLM provider is configured, and returns 503 if the gateway can't actually serve
traffic. The rich per-dependency surface for the dashboard is `/v1/system/health`
(Phase 8/20).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    app = request.app
    checks: dict[str, dict[str, object]] = {}

    for name, coro in (("postgres", app.state.db.ping()), ("redis", app.state.redis.ping())):
        start = time.perf_counter()
        ok = await coro
        checks[name] = {
            "ok": bool(ok),
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    providers = app.state.registry.available()
    checks["providers"] = {"ok": len(providers) > 0, "configured": providers}

    ready = all(c["ok"] for c in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
