"""Pydantic schemas for the HW6 clinical trial documents and the chat API."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

StatusEnum = Literal["recruiting", "active", "completed", "terminated"]
PhaseEnum = Literal["phase1", "phase2", "phase3", "phase4", "not_applicable"]


class TrialCreate(BaseModel):
    """Body for POST /api/hw6/trials."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    trialTitle: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: StatusEnum = "recruiting"
    phase: PhaseEnum
    scheduledDate: datetime


class TrialUpdate(BaseModel):
    """Body for PUT /api/hw6/trials/{id}; every field is optional."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    trialTitle: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[StatusEnum] = None
    phase: Optional[PhaseEnum] = None
    scheduledDate: Optional[datetime] = None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "TrialUpdate":
        """Reject null for fields that must always have a value."""
        required_fields = ("trialTitle", "status", "phase", "scheduledDate")
        for name in required_fields:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TrialOut(BaseModel):
    """Trial as returned by the API."""

    id: str
    trialTitle: str
    description: Optional[str] = None
    status: StatusEnum
    phase: PhaseEnum
    scheduledDate: datetime
    createdAt: datetime
    updatedAt: datetime


class ChatRequest(BaseModel):
    """Body for POST /api/chat. The last three fields are experiment knobs for Part 3."""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1, max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)
    short_term_n: Optional[int] = Field(default=None, ge=1, le=200)
    memory_policy: Optional[Literal["none", "compress_older"]] = None
    persist: bool = True
