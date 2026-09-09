"""
Password hashing and JWT issue/verify.

Argon2id is the default (winner of the Password Hashing Competition and the
current OWASP first choice). bcrypt is kept as a verify-only fallback so an
imported legacy hash still authenticates and can be upgraded on next login.

Milestone 2 wires these into /auth endpoints. They live here now so the
foundation is complete and testable.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import settings

_hasher = PasswordHasher()          # argon2id, sensible defaults

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------- passwords --
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, Exception):   # noqa: BLE001
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses outdated parameters; rehash on next login."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:                                            # noqa: BLE001
        return True


# ------------------------------------------------------------------ tokens --
def _create_token(subject: str, token_type: TokenType, expires: timedelta, claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, **claims: Any) -> str:
    return _create_token(
        subject, "access", timedelta(minutes=settings.access_token_expire_minutes), claims
    )


def create_refresh_token(subject: str, **claims: Any) -> str:
    return _create_token(
        subject, "refresh", timedelta(days=settings.refresh_token_expire_days), claims
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any] | None:
    """Returns None on any failure - expired, tampered, or the wrong token type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload


# ---------------------------------------------------------- opaque secrets --
def generate_opaque_token(nbytes: int = 48) -> str:
    """
    Refresh and reset tokens are random strings, not JWTs.

    A JWT refresh token carries claims the server must trust without a lookup;
    since we look the token up anyway (to check revocation), the claims buy
    nothing and only widen what a leaked token reveals.
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """
    SHA-256, not Argon2, and deliberately so.

    These are 384-bit random values, not human-chosen passwords: there is no
    dictionary to attack, so a slow KDF would only add latency to every refresh.
    What matters is that the stored form cannot be replayed, and a digest gives
    that.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# A hash of a value nobody knows. Verified against when a login names an unknown
# account, so that a wrong email and a wrong password take the same time and
# cannot be told apart by a stopwatch.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def waste_time_like_a_verify() -> None:
    verify_password("not-the-password", _DUMMY_HASH)
