"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.config import Settings, get_settings
from app.errors import register_exception_handlers
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from app.providers.registry import ProviderRegistry
from app.routing import Router

log = get_logger("gateway.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.registry = ProviderRegistry(settings)
        app.state.router = Router(app.state.registry, settings)
        log.info(
            "gateway.startup",
            version=__version__,
            environment=settings.environment,
            default_provider=settings.default_provider,
            providers_available=app.state.registry.available(),
        )
        try:
            yield
        finally:
            await app.state.registry.aclose()
            log.info("gateway.shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Multi-provider LLM gateway with retries, fallback, caching and observability.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(chat_router)

    return app


app = create_app()
