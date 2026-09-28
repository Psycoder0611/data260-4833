from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth_utils import verify_password
from database import get_db
from models import SessionDB, UserDB
from fastapi import APIRouter, Depends, HTTPException, Request, Response 


router = APIRouter(
    prefix="/api",
    tags=["HW4 Authentication"]
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user = (
        db.query(UserDB)
        .filter(UserDB.email == login_data.email)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    session_token = secrets.token_urlsafe(32)

    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=1)

    session = SessionDB(
        id=session_token,
        user_id=user.id,
        created_at=created_at,
        expires_at=expires_at
    )

    db.add(session)
    db.commit()

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=3600
    )

    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email
        }
    }

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    session_token = request.cookies.get("session_token")

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Login required"
        )

    session = (
        db.query(SessionDB)
        .filter(SessionDB.id == session_token)
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid session"
        )

    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired"
        )

    user = (
        db.query(UserDB)
        .filter(UserDB.id == session.user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user


@router.get("/me")
def get_me(
    current_user: UserDB = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email
    }