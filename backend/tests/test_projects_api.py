"""Phase 8: project / API-key CRUD (create shows the key once, rotate, revoke)."""

from __future__ import annotations

from httpx import AsyncClient

from app.security import KEY_PREFIX


async def test_requires_admin(client: AsyncClient) -> None:
    assert (await client.post("/v1/projects", json={"name": "x"})).status_code == 401
    assert (await client.get("/v1/projects")).status_code == 401


async def test_create_rotate_revoke_lifecycle(admin_client: AsyncClient) -> None:
    # create
    created = await admin_client.post(
        "/v1/projects", json={"name": "RAG App", "rate_limit_per_minute": 120}
    )
    assert created.status_code == 201
    body = created.json()
    full_key = body["api_key"]
    assert full_key.startswith(KEY_PREFIX)
    assert body["key_prefix"] != full_key and full_key.startswith(body["key_prefix"])
    assert body["rate_limit_per_minute"] == 120
    pid = body["id"]

    # the created key actually works against the gateway
    r = await admin_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {full_key}"},
    )
    assert r.status_code == 200

    # list — never leaks the full key
    listed = (await admin_client.get("/v1/projects")).json()["projects"]
    row = next(p for p in listed if p["id"] == pid)
    assert row["name"] == "RAG App"
    assert "api_key" not in row and row["key_prefix"].startswith(KEY_PREFIX)

    # rotate — new key, old one stops working
    rotated = await admin_client.post(f"/v1/projects/{pid}/rotate")
    assert rotated.status_code == 200
    new_key = rotated.json()["api_key"]
    assert new_key != full_key
    old = await admin_client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {full_key}"},
    )
    assert old.status_code == 401  # revoked hash

    # revoke — the new key is rejected too
    rev = await admin_client.post(f"/v1/projects/{pid}/revoke")
    assert rev.status_code == 200 and rev.json()["status"] == "revoked"
    after = await admin_client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {new_key}"},
    )
    assert after.status_code == 401


async def test_unknown_project_id_is_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.post("/v1/projects/not-a-uuid/revoke")).status_code == 404
    assert (
        await admin_client.post("/v1/projects/00000000-0000-0000-0000-000000000000/rotate")
    ).status_code == 404
