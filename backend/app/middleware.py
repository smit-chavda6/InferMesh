"""Pure-ASGI request-context middleware.

Implemented at the ASGI layer (rather than ``BaseHTTPMiddleware``) so it stays
transparent to streaming responses introduced in Phase 5.

Responsibilities:
  * assign/propagate a request id (``X-Request-ID``)
  * expose it as ``request.state.request_id``
  * bind per-request logging context
  * emit start/end access logs with duration
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import get_logger

REQUEST_ID_HEADER = "x-request-id"
log = get_logger("gateway.access")


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        request_id = headers.get(REQUEST_ID_HEADER) or _new_request_id()

        # Starlette builds Request.state from scope["state"].
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        start = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, method=method, path=path)
        log.info("request.start")

        status_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                raw_headers = list(message.get("headers", []))
                raw_headers.append(
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1"))
                )
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.exception("request.error", duration_ms=duration_ms)
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info("request.end", status_code=status_holder["code"], duration_ms=duration_ms)
