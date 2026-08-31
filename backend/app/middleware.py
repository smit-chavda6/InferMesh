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

import json
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import get_logger

REQUEST_ID_HEADER = "x-request-id"
_DEFAULT_MAX_BODY_BYTES = 5_000_000
log = get_logger("gateway.access")


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


async def _send_json(send: Send, status: int, body: dict[str, object], request_id: str) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                # We reject before draining the request body; close so clients that
                # are still uploading don't hang waiting for a keep-alive response.
                (b"connection", b"close"),
                (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


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

        # Reject oversized bodies before reading them.
        app = scope.get("app")
        max_body = getattr(
            getattr(getattr(app, "state", None), "settings", None),
            "max_request_body_bytes",
            _DEFAULT_MAX_BODY_BYTES,
        )
        content_length = headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > max_body:
            log.warning(
                "request.body_too_large", content_length=int(content_length), limit=max_body
            )
            await _send_json(
                send,
                413,
                {
                    "error": {
                        "type": "request_too_large",
                        "message": f"request body exceeds {max_body} bytes",
                        "request_id": request_id,
                    }
                },
                request_id,
            )
            return

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
