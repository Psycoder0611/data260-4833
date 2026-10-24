"""FastAPI dependencies for JWT login checks and role checks."""

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from hw7.db import HW7User, get_users_db
from hw7.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def unauthorized(detail: str) -> HTTPException:
    """Build a 401 error with the Bearer challenge header."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_users_db),
) -> HW7User:
    """Return the user named in a valid token, otherwise raise 401."""
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized("Could not validate credentials") from exc

    user = db.query(HW7User).filter(HW7User.username == payload["sub"]).first()
    if user is None:
        raise unauthorized("Could not validate credentials")
    return user


def require_roles(*allowed_roles: str) -> Callable[..., HW7User]:
    """Return a dependency that lets only the given roles through (else 403)."""

    def role_checker(current_user: HW7User = Depends(get_current_user)) -> HW7User:
        """Raise 403 when the logged-in user's role is not allowed."""
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not allowed to do this",
            )
        return current_user

    return role_checker
