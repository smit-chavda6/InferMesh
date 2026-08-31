from __future__ import annotations

from app.security import KEY_PREFIX, generate_api_key, hash_api_key, key_display_prefix


def test_generate_api_key_shape() -> None:
    key = generate_api_key()
    assert key.startswith(KEY_PREFIX)
    assert len(key) > len(KEY_PREFIX) + 20
    assert generate_api_key() != generate_api_key()


def test_hash_is_stable_sha256_hex() -> None:
    key = "sk-gw-abc123"
    h = hash_api_key(key)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert hash_api_key(key) == h


def test_display_prefix_is_short_and_non_secret() -> None:
    key = generate_api_key()
    prefix = key_display_prefix(key)
    assert prefix.startswith(KEY_PREFIX)
    assert len(prefix) == len(KEY_PREFIX) + 4
    assert prefix != key
    assert key.startswith(prefix)
