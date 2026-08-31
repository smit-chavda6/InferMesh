"""Dashboard admin auth: `POST /v1/auth/{login,logout,refresh}` + `GET /v1/auth/me`."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.auth import REFRESH_COOKIE, AdminAuth, AdminDep
from app.errors import AdminAuthError
from app.logging_config import get_logger
from app.ratelimit import RateLimiter

router = APIRouter(prefix="/v1/auth", tags=["auth"])
log = get_logger(__name__)

_LOGIN_LIMIT = 10  # attempts
_LOGIN_WINDOW = 300  # seconds, per client IP


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class AdminInfo(BaseModel):
    email: str


@router.post("/login", response_model=AdminInfo)
async def login(body: LoginBody, request: Request, response: Response) -> AdminInfo:
    auth: AdminAuth = request.app.state.admin_auth
    limiter: RateLimiter = request.app.state.rate_limiter

    client_ip = request.client.host if request.client else "unknown"
    rl = await limiter.check(f"login:{client_ip}", _LOGIN_LIMIT, _LOGIN_WINDOW)
    if not rl.allowed:
        raise AdminAuthError("too many login attempts; try again later")

    if not auth.check_credentials(body.email, body.password):
        log.warning("auth.login_failed", ip=client_ip)
        raise AdminAuthError("invalid email or password")

    tokens = auth.issue(subject=body.email.lower())
    auth.set_cookies(response, tokens)
    log.info("auth.login_ok", email=body.email.lower())
    return AdminInfo(email=body.email.lower())


@router.post("/refresh", response_model=AdminInfo)
async def refresh(request: Request, response: Response) -> AdminInfo:
    auth: AdminAuth = request.app.state.admin_auth
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AdminAuthError("no refresh token")

    claims = auth.decode(token, "refresh")
    jti = str(claims.get("jti", ""))
    if await auth.is_refresh_revoked(jti):
        raise AdminAuthError("refresh token has been revoked")

    subject = str(claims.get("sub", ""))
    # Rotate: revoke the old refresh token, issue a fresh pair.
    await auth.revoke_refresh(jti, int(claims.get("exp", 0)))
    tokens = auth.issue(subject=subject)
    auth.set_cookies(response, tokens)
    return AdminInfo(email=subject)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    auth: AdminAuth = request.app.state.admin_auth
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            claims = auth.decode(token, "refresh")
            await auth.revoke_refresh(str(claims.get("jti", "")), int(claims.get("exp", 0)))
        except AdminAuthError:
            pass  # already invalid — nothing to revoke
    auth.clear_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=AdminInfo)
async def me(admin: AdminDep) -> AdminInfo:
    return AdminInfo(email=admin.email)
