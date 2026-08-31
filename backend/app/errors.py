"""Gateway error types and FastAPI exception handlers.

All errors surface as a consistent JSON envelope::

    {"error": {"type": "provider_timeout", "message": "...", "request_id": "req_..."}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_logger

log = get_logger(__name__)


class GatewayError(Exception):
    """Base class for all gateway-raised errors."""

    error_type: str = "gateway_error"
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProviderNotConfiguredError(GatewayError):
    error_type = "provider_not_configured"
    status_code = 503

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class ProviderError(GatewayError):
    """Upstream provider failed in a way the gateway could not recover from."""

    error_type = "provider_error"
    status_code = 502

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class ProviderTimeoutError(ProviderError):
    error_type = "provider_timeout"
    status_code = 504


class ProviderRateLimitError(ProviderError):
    error_type = "provider_rate_limited"
    status_code = 429


class ProviderAuthError(ProviderError):
    error_type = "provider_auth_error"
    status_code = 502


class ProviderBadRequestError(ProviderError):
    """The upstream rejected the request payload (4xx that is the caller's fault)."""

    error_type = "provider_bad_request"
    status_code = 400


class AllProvidersFailedError(GatewayError):
    error_type = "all_providers_failed"
    status_code = 502


def _envelope(error_type: str, message: str, request_id: str | None) -> dict[str, object]:
    return {"error": {"type": error_type, "message": message, "request_id": request_id}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GatewayError)
    async def _gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.warning(
            "gateway.error",
            error_type=exc.error_type,
            status_code=exc.status_code,
            message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.error_type, exc.message, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "type": "validation_error",
                    "message": "Request body failed validation.",
                    "request_id": request_id,
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail), request_id),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.exception("gateway.unhandled_exception")
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "An unexpected error occurred.", request_id),
        )
