from __future__ import annotations

from app.security import hash_password, hash_session_token, verify_password


def test_password_hash_is_salted_scrypt_and_never_plaintext():
    first = hash_password("123456")
    second = hash_password("123456")
    assert first.startswith("scrypt$v=1$")
    assert first != second
    assert "123456" not in first
    assert verify_password("123456", first)
    assert not verify_password("wrong", first)


def test_session_token_is_stored_as_one_way_digest():
    raw = "session-token-for-test"
    digest = hash_session_token(raw)
    assert raw not in digest
    assert len(digest) == 64
