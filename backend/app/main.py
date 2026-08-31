"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.requests import router as requests_router
from app.cache import ChatCache, Embedder
from app.config import Settings, get_settings
from app.db.session import Database
from app.errors import register_exception_handlers
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestContextMiddleware
from app.observability import UsageRecorder
from app.pricing import get_pricing_table
from app.providers.registry import ProviderRegistry
from app.ratelimit import RateLimiter
from app.redis_client import RedisClient
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
        app.state.db = Database(settings)
        app.state.pricing = get_pricing_table()
        app.state.recorder = UsageRecorder(
            app.state.db, app.state.pricing, enabled=settings.usage_logging_enabled
        )
        app.state.redis = RedisClient(settings)
        app.state.rate_limiter = RateLimiter(
            app.state.redis, fail_open=settings.rate_limit_fail_open
        )
        app.state.embedder = Embedder(settings)
        app.state.cache = ChatCache(
            app.state.redis.client,
            app.state.db.sessionmaker,
            app.state.embedder,
            settings,
            app.state.pricing,
        )
        db_ok = await app.state.db.ping()
        redis_ok = await app.state.redis.ping()
        for warning in settings.startup_warnings():
            log.warning("gateway.startup_warning", detail=warning)
        log.info(
            "gateway.startup",
            version=__version__,
            environment=settings.environment,
            default_provider=settings.default_provider,
            providers_available=app.state.registry.available(),
            pricing_version=app.state.pricing.version,
            database_reachable=db_ok,
            redis_reachable=redis_ok,
            cache_enabled=settings.cache_enabled,
            semantic_cache=app.state.cache.semantic_enabled,
            rate_limit_enabled=settings.rate_limit_enabled,
        )
        try:
            yield
        finally:
            await app.state.registry.aclose()
            await app.state.embedder.aclose()
            await app.state.redis.close()
            await app.state.db.dispose()
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
    app.include_router(requests_router)

    return app


app = create_app()
