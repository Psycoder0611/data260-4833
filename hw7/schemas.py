"""Pydantic schemas for the HW7 auth and trial routes."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Body returned by POST /auth/login."""

    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    """Body returned by GET /auth/me."""

    id: int
    username: str
    role: str


class TrialCreate(BaseModel):
    """Body for POST /api/hw7/trials (same fields as the HW5 create)."""

    trialTitle: str = Field(min_length=2, max_length=255)
    trial_code: str = Field(min_length=3, max_length=100)
    participant_capacity: int = Field(default=100, ge=1)
    organization_id: int = Field(ge=1)


class TrialOut(BaseModel):
    """One clinical trial in a response."""

    id: int
    trialTitle: str
    sponsor: str
    trial_code: Optional[str]
    participant_capacity: int
    organization_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
