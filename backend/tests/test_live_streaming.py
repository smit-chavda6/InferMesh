"""Live Phase 5 check: real SSE streaming + usage row, per provider.

Skipped unless the matching key is configured. Run with ``uv run pytest -m live``.
"""

from __future__ import annotations

import json
import os

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import RequestLog
from app.main import create_app

pytestmark = pytest.mark.live


def _events(text: str) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


async def _run(provider: str, model: str) -> None:
    settings = Settings()
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://gateway.test") as http,
            http.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "provider": provider,
                    "model": model,
                    "messages": [{"role": "user", "content": "Count: one two three."}],
                    "max_tokens": 512,
                    "stream": True,
                },
            ) as resp,
        ):
            assert resp.status_code == 200, await resp.aread()
            assert resp.headers["content-type"].startswith("text/event-stream")
            text = "".join([c async for c in resp.aiter_text()])

    assert text.rstrip().endswith("data: [DONE]")
    events = _events(text)
    content = "".join(
        e["choices"][0]["delta"].get("content", "")
        for e in events
        if e.get("choices") and e["choices"][0]["delta"].get("content")
    )
    assert content.strip(), "no streamed content"
    final = events[-1]
    assert final["gateway"]["provider"] == provider
    assert final["usage"]["total_tokens"] > 0
    request_id = final["gateway"]["request_id"]

    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as session:
            row = (
                await session.execute(select(RequestLog).where(RequestLog.request_id == request_id))
            ).scalar_one()
        assert row.streamed is True
        assert row.status == "success"
        assert row.total_tokens == final["usage"]["total_tokens"]
        assert row.cost_usd is not None
    finally:
        await engine.dispose()


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not configured")
async def test_live_stream_openai() -> None:
    settings = Settings()
    model = (
        settings.azure_openai_deployment
        if settings.openai_mode == "azure"
        else settings.openai_default_model
    )
    await _run("openai", model or "")


@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not configured")
async def test_live_stream_gemini() -> None:
    await _run("gemini", Settings().gemini_default_model)
