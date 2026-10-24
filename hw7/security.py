"""Password hashing (bcrypt) and JWT helpers for HW7."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from auth_utils import hash_password, verify_password
from hw7 import config

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]


def create_access_token(
    username: str,
    role: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """Return a signed JWT for username with the role and an expiry time."""
    minutes = (
        config.ACCESS_TOKEN_EXPIRE_MINUTES
        if expires_minutes is None
        else expires_minutes
    )
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Check the signature and expiry of token and return its claims.

    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError when the token is bad.
    """
    return jwt.decode(
        token,
        config.JWT_SECRET_KEY,
        algorithms=[config.JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
