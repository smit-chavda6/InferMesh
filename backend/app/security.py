"""Gateway client API-key helpers.

Keys are random opaque tokens shown in full exactly once at creation, stored only
as SHA-256 hashes, and referenced afterward by a short prefix (spec §2.1). The
admin/dashboard auth system (bcrypt + JWT) is separate and lands in Phase 8.
"""

from __future__ import annotations

import hashlib
import secrets

KEY_PREFIX = "sk-gw-"
_TOKEN_BYTES = 24  # -> 32 url-safe chars


def generate_api_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_urlsafe(_TOKEN_BYTES)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_display_prefix(key: str) -> str:
    """Short, non-secret reference shown in the UI, e.g. ``sk-gw-7f92``."""
    body = key[len(KEY_PREFIX) :] if key.startswith(KEY_PREFIX) else key
    return f"{KEY_PREFIX}{body[:4]}"
