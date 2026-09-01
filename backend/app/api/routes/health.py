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

import datetime as dt
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app import __version__
from app import metrics as _metrics

router = APIRouter(tags=["system"])

# Baked at image build time (see docker/frontend.Dockerfile / backend Dockerfile).
_GIT_SHA = os.getenv("GIT_SHA", "dev")
_BUILD_TIME = os.getenv("BUILD_TIME") or None
_STARTED_AT = dt.datetime.now(dt.UTC)


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


@router.get("/v1/version")
async def version() -> dict[str, object]:
    """Build provenance — useful to confirm what's actually deployed."""
    return {
        "version": __version__,
        "git_sha": _GIT_SHA,
        "build_time": _BUILD_TIME,
        "started_at": _STARTED_AT.isoformat(),
    }


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus exposition. Open by default; set METRICS_TOKEN to require
    ``Authorization: Bearer <token>``."""
    settings = request.app.state.settings
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    token = settings.metrics_token
    if token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="metrics token required")
    body, content_type = _metrics.render()
    return Response(content=body, media_type=content_type)
