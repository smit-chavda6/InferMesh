"""Dashboard admin authentication — single-admin, bcrypt password + JWT cookies.

Completely separate from the gateway *client* API keys (`app/security.py`,
`app/api/deps.py`): those authorize `/v1/chat/completions`; this authorizes the
read-only dashboard endpoints.

Login issues a short-lived access token and a longer refresh token, both as
HttpOnly cookies. Logout adds the refresh token's ``jti`` to a Redis denylist
(TTL = its remaining life) so it can't be exchanged again; access tokens are
short enough that clearing the cookie is sufficient.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import bcrypt
import jwt
from fastapi import Depends, Request, Response

from app.config import Settings
from app.errors import AdminAuthError
from app.logging_config import get_logger
from app.redis_client import RedisClient

log = get_logger(__name__)

ACCESS_COOKIE = "gw_access"
REFRESH_COOKIE = "gw_refresh"
_ALG = "HS256"
_REVOKED_PREFIX = "auth:revoked:"


def hash_password(plain: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


@dataclass(slots=True)
class AdminIdentity:
    email: str


@dataclass(slots=True)
class IssuedTokens:
    access: str
    refresh: str
    refresh_jti: str
    refresh_expires_at: int


class AdminAuth:
    def __init__(self, settings: Settings, redis: RedisClient) -> None:
        self._settings = settings
        self._redis = redis
        # Hash the configured password once at startup; compared on every login.
        self._pw_hash = hash_password(settings.admin_password, settings.bcrypt_rounds)

    # -- credentials -----------------------------------------------------

    def check_credentials(self, email: str, password: str) -> bool:
        email_ok = email.strip().lower() == self._settings.admin_email.strip().lower()
        pw_ok = verify_password(password, self._pw_hash)
        return email_ok and pw_ok

    # -- tokens --------------------------------------------------------

    def _encode(
        self, subject: str, token_type: Literal["access", "refresh"], ttl: int
    ) -> tuple[str, str, int]:
        now = int(time.time())
        exp = now + ttl
        jti = uuid.uuid4().hex
        payload = {"sub": subject, "type": token_type, "iat": now, "exp": exp, "jti": jti}
        token = jwt.encode(payload, self._settings.jwt_secret, algorithm=_ALG)
        return token, jti, exp

    def issue(self, subject: str) -> IssuedTokens:
        access, _, _ = self._encode(subject, "access", self._settings.jwt_access_ttl_seconds)
        refresh, rjti, rexp = self._encode(
            subject, "refresh", self._settings.jwt_refresh_ttl_seconds
        )
        return IssuedTokens(
            access=access, refresh=refresh, refresh_jti=rjti, refresh_expires_at=rexp
        )

    def decode(self, token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any]:
        try:
            claims = jwt.decode(token, self._settings.jwt_secret, algorithms=[_ALG])
        except jwt.ExpiredSignatureError as exc:
            raise AdminAuthError("session expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AdminAuthError("invalid session token") from exc
        if claims.get("type") != expected_type:
            raise AdminAuthError("wrong token type")
        return claims

    # -- revocation (refresh tokens) -----------------------------------

    async def revoke_refresh(self, jti: str, expires_at: int) -> None:
        ttl = max(expires_at - int(time.time()), 1)
        try:
            await self._redis.client.set(f"{_REVOKED_PREFIX}{jti}", "1", ex=ttl)
        except Exception as exc:  # noqa: BLE001 - logout is best-effort if Redis is down
            log.warning("auth.revoke_failed", error=str(exc))

    async def is_refresh_revoked(self, jti: str) -> bool:
        try:
            return bool(await self._redis.client.exists(f"{_REVOKED_PREFIX}{jti}"))
        except Exception as exc:  # noqa: BLE001 - availability over the narrow revocation guarantee
            log.warning("auth.revocation_check_failed", error=str(exc))
            return False

    # -- cookies ------------------------------------------------------

    def set_cookies(self, response: Response, tokens: IssuedTokens) -> None:
        s = self._settings
        for name, value, ttl in (
            (ACCESS_COOKIE, tokens.access, s.jwt_access_ttl_seconds),
            (REFRESH_COOKIE, tokens.refresh, s.jwt_refresh_ttl_seconds),
        ):
            response.set_cookie(
                name,
                value,
                max_age=ttl,
                httponly=True,
                secure=s.auth_cookie_secure,
                samesite=s.auth_cookie_samesite,
                path="/",
            )

    def clear_cookies(self, response: Response) -> None:
        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            response.delete_cookie(name, path="/")


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def require_admin(request: Request) -> AdminIdentity:
    """FastAPI dependency: 401 unless a valid admin access token is present
    (cookie preferred; ``Authorization: Bearer`` accepted for API clients)."""
    auth: AdminAuth = request.app.state.admin_auth
    token = request.cookies.get(ACCESS_COOKIE) or _bearer(request)
    if not token:
        raise AdminAuthError("admin session required")
    claims = auth.decode(token, "access")
    return AdminIdentity(email=str(claims.get("sub", "")))


AdminDep = Annotated[AdminIdentity, Depends(require_admin)]
