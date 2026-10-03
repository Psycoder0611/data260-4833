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


# ---------------------------------------------------------
# HW5 Related Entity
# ---------------------------------------------------------

class ResearchOrganizationDB(Base):
    __tablename__ = "research_organizations"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    name = Column(
        String(255),
        nullable=False
    )

    country = Column(
        String(100),
        nullable=False
    )

    contact_email = Column(
        String(255),
        unique=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    trials = relationship(
        "ClinicalTrialDB",
        back_populates="organization"
    )


# ---------------------------------------------------------
# Primary Domain Entity
# ---------------------------------------------------------

class ClinicalTrialDB(Base):
    __tablename__ = "clinical_trials"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    # Existing HW4 field
    trialTitle = Column(
        String(255),
        nullable=False
    )

    # Existing HW4 field retained for backward compatibility
    sponsor = Column(
        String(255),
        nullable=False
    )

    # HW5 unique field
    trial_code = Column(
        String(100),
        unique=True,
        nullable=True
    )

    # HW5 numeric field
    participant_capacity = Column(
        Integer,
        default=100,
        nullable=False
    )

    # HW5 related-entity foreign key
    organization_id = Column(
        Integer,
        ForeignKey(
            "research_organizations.id",
            ondelete="RESTRICT"
        ),
        nullable=True
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

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    organization = relationship(
        "ResearchOrganizationDB",
        back_populates="trials"
    )

    notes = relationship(
        "TrialNoteDB",
        back_populates="trial"
    )


# ---------------------------------------------------------
# HW4 Related Notes Table
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Authentication Tables
# ---------------------------------------------------------

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