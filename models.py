from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class ClinicalTrialDB(Base):
    __tablename__ = "clinical_trials"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    trialTitle = Column(
        String(255),
        nullable=False
    )

    sponsor = Column(
        String(255),
        nullable=False
    )

    submitterEmail = Column(
        String(255),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    category = Column(
        String(100),
        nullable=True
    )

    notes = relationship(
        "TrialNoteDB",
        back_populates="trial"
    )


class TrialNoteDB(Base):
    __tablename__ = "trial_notes"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    trial_id = Column(
        Integer,
        ForeignKey("clinical_trials.id"),
        nullable=False
    )

    note = Column(
        String(255),
        nullable=False
    )

    trial = relationship(
        "ClinicalTrialDB",
        back_populates="notes"
    )


class UserDB(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    sessions = relationship(
        "SessionDB",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class SessionDB(Base):
    __tablename__ = "sessions"

    id = Column(
        String(128),
        primary_key=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    expires_at = Column(
        DateTime,
        nullable=False
    )

    user = relationship(
        "UserDB",
        back_populates="sessions"
    )