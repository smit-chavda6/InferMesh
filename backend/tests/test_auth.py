"""Phase 8: dashboard admin auth (login / refresh / logout / me)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def _cookie(resp, name: str) -> str | None:
    """Read a Set-Cookie value straight off a response (avoids jar conflicts)."""
    for raw in resp.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw.split(";", 1)[0].split("=", 1)[1]
    return None


async def test_full_auth_flow(app_with_mocks) -> None:
    transport = ASGITransport(app=app_with_mocks)
    async with AsyncClient(transport=transport, base_url="http://gw.test") as c:
        # unauthenticated → 401
        assert (await c.get("/v1/auth/me")).status_code == 401
        assert (await c.get("/v1/usage/summary")).status_code == 401

        # wrong password → 401
        bad = await c.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "nope"})
        assert bad.status_code == 401
        assert bad.json()["error"]["type"] == "admin_auth_required"

        # login → cookies set, protected routes now work
        ok = await c.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert ok.status_code == 200 and ok.json()["email"] == ADMIN_EMAIL
        assert _cookie(ok, "gw_access") and _cookie(ok, "gw_refresh")
        refresh_1 = _cookie(ok, "gw_refresh")

        me = await c.get("/v1/auth/me")
        assert me.status_code == 200 and me.json()["email"] == ADMIN_EMAIL
        assert (await c.get("/v1/usage/summary")).status_code == 200

        # refresh rotates the pair
        r = await c.post("/v1/auth/refresh", cookies={"gw_refresh": refresh_1})
        assert r.status_code == 200
        refresh_2 = _cookie(r, "gw_refresh")
        assert refresh_2 and refresh_2 != refresh_1

        # the rotated-out refresh token is revoked
        again = await c.post("/v1/auth/refresh", cookies={"gw_refresh": refresh_1})
        assert again.status_code == 401

        # logout revokes the current refresh + clears cookies
        access_2 = _cookie(r, "gw_access")
        lo = await c.post(
            "/v1/auth/logout", cookies={"gw_refresh": refresh_2, "gw_access": access_2}
        )
        assert lo.status_code == 200
        dead = await c.post("/v1/auth/refresh", cookies={"gw_refresh": refresh_2})
        assert dead.status_code == 401


async def test_login_email_case_insensitive(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/auth/login", json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD}
    )
    assert resp.status_code == 200


async def test_garbage_token_rejected(admin_client: AsyncClient) -> None:
    admin_client.cookies.set("gw_access", "not-a-jwt")
    assert (await admin_client.get("/v1/auth/me")).status_code == 401
