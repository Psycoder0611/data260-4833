"""HW7 Part 1: POST /auth/login and GET /auth/me (JWT bearer tokens)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from hw7.db import HW7User, get_users_db
from hw7.deps import get_current_user
from hw7.schemas import MeResponse, TokenResponse
from hw7.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["HW7 Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_users_db),
) -> dict:
    """Check username and password against MySQL and return a JWT on success."""
    user = db.query(HW7User).filter(HW7User.username == form_data.username).first()
    # Same message for an unknown user and a wrong password.
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.username, user.role)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=MeResponse)
def read_me(current_user: HW7User = Depends(get_current_user)) -> HW7User:
    """Return the identity and role of the logged-in user."""
    return current_user
