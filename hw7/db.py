"""MySQL connection and the users table for HW7 (database s4833_hw7)."""

from typing import Iterator

from sqlalchemy import Column, Enum, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from hw7 import config

# A separate Base keeps this users table out of the HW4/HW5 metadata.
Base = declarative_base()

engine = create_engine(config.HW7_DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class HW7User(Base):
    """One login account: unique username, bcrypt hash and a role."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(*config.ROLES, name="user_role"), nullable=False)


def get_users_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session for the HW7 users database."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
