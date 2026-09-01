"""FX rate helper + GET /v1/fx (display-only currency switch)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app import fx
from app.config import Settings

from .conftest import make_settings


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, k: str) -> str | None:
        return self.store.get(k)

    async def set(self, k: str, v: str, ex: int | None = None) -> None:
        self.store[k] = v


def _settings(**over: Any) -> Settings:
    # the offline suite disables FX by default (no network); the fetch-path tests
    # opt back in explicitly.
    return make_settings(**{"fx_enabled": True, **over})


async def test_fetches_parses_and_caches() -> None:
    calls = 0

    async def http_get(url: str, params: dict[str, str]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"base": "USD", "date": "2026-09-01", "rates": {"INR": 87.1234}}

    r = _FakeRedis()
    first = await fx.usd_inr(r, _settings(), http_get=http_get)
    assert first == {"rate": 87.1234, "source": "frankfurter", "as_of": "2026-09-01"}

    # second call is served from the cache — no second fetch
    second = await fx.usd_inr(r, _settings(), http_get=http_get)
    assert second == first
    assert calls == 1


async def test_falls_back_when_the_fetch_fails() -> None:
    async def boom(url: str, params: dict[str, str]) -> dict[str, Any]:
        raise RuntimeError("network down")

    out = await fx.usd_inr(_FakeRedis(), _settings(fx_usd_inr_fallback=90.0), http_get=boom)
    assert out == {"rate": 90.0, "source": "fallback", "as_of": None}


async def test_disabled_returns_fallback_without_touching_the_network() -> None:
    async def boom(url: str, params: dict[str, str]) -> dict[str, Any]:
        raise AssertionError("should not be called")

    out = await fx.usd_inr(_FakeRedis(), _settings(fx_enabled=False), http_get=boom)
    assert out["source"] == "fallback"


async def test_fx_endpoint_shape_and_admin_gate(
    admin_client: AsyncClient, client: AsyncClient
) -> None:
    assert (await client.get("/v1/fx")).status_code == 401  # admin only

    body = (await admin_client.get("/v1/fx")).json()
    assert body["base"] == "USD"
    assert body["rates"]["USD"] == 1.0
    assert body["rates"]["INR"] > 0
    assert body["source"] in {"frankfurter", "fallback"}


@pytest.mark.live
async def test_frankfurter_is_reachable() -> None:
    out = await fx.usd_inr(_FakeRedis(), _settings())
    assert out["source"] == "frankfurter"
    assert 50 < out["rate"] < 150
