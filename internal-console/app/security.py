from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt$v=1$n={SCRYPT_N}$r={SCRYPT_R}$p={SCRYPT_P}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, version, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$")
        if algorithm != "scrypt" or version != "v=1":
            return False
        n = int(n_raw.removeprefix("n="))
        r = int(r_raw.removeprefix("r="))
        p = int(p_raw.removeprefix("p="))
        if (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
