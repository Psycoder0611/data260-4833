"""Offline tests for HW7 (SQLite in memory). No MySQL, Docker or Ollama needed."""

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import init_hw7_db
import models
from database import get_db
from hw7 import config
from hw7.db import Base as UsersBase
from hw7.db import HW7User, get_users_db
from hw7.security import create_access_token, hash_password, verify_password
from routers import hw7_auth, hw7_trials


def memory_engine():
    """Return a fresh in-memory SQLite engine that can be shared by test threads."""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def client():
    """App with the HW7 routers, an empty users DB and a small trials DB."""
    users_engine = memory_engine()
    trials_engine = memory_engine()
    UsersBase.metadata.create_all(users_engine)
    models.Base.metadata.create_all(trials_engine)
    UsersSession = sessionmaker(bind=users_engine)
    TrialsSession = sessionmaker(bind=trials_engine)

    with UsersSession() as session:
        for username, password, role in config.DEMO_USERS:
            session.add(
                HW7User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                )
            )
        session.commit()
    with TrialsSession() as session:
        session.add(
            models.ResearchOrganizationDB(
                name="Test Org", country="US", contact_email="org@example.com"
            )
        )
        session.commit()

    def users_db():
        with UsersSession() as session:
            yield session

    def trials_db():
        with TrialsSession() as session:
            yield session

    app = FastAPI()
    app.include_router(hw7_auth.router)
    app.include_router(hw7_trials.router)
    app.dependency_overrides[get_users_db] = users_db
    app.dependency_overrides[get_db] = trials_db
    return TestClient(app)


def login(client, username):
    """Log in a demo user and return the Authorization header."""
    password = next(p for u, p, _ in config.DEMO_USERS if u == username)
    response = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


TRIAL = {
    "trialTitle": "Offline Test Trial",
    "trial_code": "OFF-001",
    "participant_capacity": 50,
    "organization_id": 1,
}


def test_password_is_hashed_not_plain():
    """The stored value is a bcrypt hash that verifies, never the plain text."""
    stored = hash_password("Secret#1")
    assert stored != "Secret#1" and stored.startswith("$2")
    assert verify_password("Secret#1", stored)
    assert not verify_password("wrong", stored)


def test_login_returns_token_with_role(client):
    """Valid credentials give a JWT that carries the username and role."""
    headers = login(client, "writer_user")
    claims = jwt.decode(
        headers["Authorization"].split()[1],
        config.JWT_SECRET_KEY,
        algorithms=[config.JWT_ALGORITHM],
    )
    assert claims["sub"] == "writer_user" and claims["role"] == "writer"


def test_login_wrong_password_and_unknown_user_give_401(client):
    """Both failures return 401 with the same message."""
    bad_password = client.post(
        "/auth/login", data={"username": "writer_user", "password": "nope"}
    )
    unknown = client.post("/auth/login", data={"username": "ghost", "password": "x"})
    assert bad_password.status_code == unknown.status_code == 401
    assert bad_password.json() == unknown.json()


def test_me_without_token_is_401(client):
    """No Authorization header means 401."""
    assert client.get("/auth/me").status_code == 401


def test_me_with_invalid_token_is_401(client):
    """A garbage token and a token signed with another key both give 401."""
    garbage = client.get("/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    forged = jwt.encode(
        {"sub": "writer_user", "exp": 9999999999},
        "other-key-that-is-long-enough-123",
        "HS256",
    )
    forged_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert garbage.status_code == 401
    assert forged_response.status_code == 401


def test_me_with_expired_token_is_401(client):
    """A correctly signed token that has expired gives 401."""
    token = create_access_token("writer_user", "writer", expires_minutes=-5)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_me_returns_identity_and_role(client):
    """A valid token returns the user's id, username and role."""
    response = client.get("/auth/me", headers=login(client, "reader_user"))
    assert response.status_code == 200
    assert response.json()["username"] == "reader_user"
    assert response.json()["role"] == "reader"


def test_token_for_deleted_user_is_401(client):
    """A valid signature is not enough if the user no longer exists."""
    token = create_access_token("ghost", "moderator")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_reader_cannot_create(client):
    """reader gets 403 on create."""
    response = client.post(
        "/api/hw7/trials", json=TRIAL, headers=login(client, "reader_user")
    )
    assert response.status_code == 403


@pytest.mark.parametrize("username", ["writer_user", "moderator_user"])
def test_writer_and_moderator_can_create(client, username):
    """writer and moderator both get 201 on create."""
    response = client.post(
        "/api/hw7/trials", json=TRIAL, headers=login(client, username)
    )
    assert response.status_code == 201
    assert response.json()["trial_code"] == "OFF-001"


def test_create_duplicate_code_is_409_and_bad_org_is_404(client):
    """Domain errors still work behind the role check."""
    headers = login(client, "writer_user")
    assert (
        client.post("/api/hw7/trials", json=TRIAL, headers=headers).status_code == 201
    )
    assert (
        client.post("/api/hw7/trials", json=TRIAL, headers=headers).status_code == 409
    )
    other = {**TRIAL, "trial_code": "OFF-002", "organization_id": 99}
    assert (
        client.post("/api/hw7/trials", json=other, headers=headers).status_code == 404
    )


def test_create_without_token_is_401(client):
    """No token on create gives 401, not 403."""
    assert client.post("/api/hw7/trials", json=TRIAL).status_code == 401


def test_delete_only_moderator(client):
    """writer gets 403, moderator gets 200, and the trial is gone afterwards."""
    writer = login(client, "writer_user")
    moderator = login(client, "moderator_user")
    trial_id = client.post("/api/hw7/trials", json=TRIAL, headers=writer).json()["id"]
    assert (
        client.delete(f"/api/hw7/trials/{trial_id}", headers=writer).status_code == 403
    )
    assert (
        client.delete(f"/api/hw7/trials/{trial_id}", headers=moderator).status_code
        == 200
    )
    assert (
        client.get(f"/api/hw7/trials/{trial_id}", headers=moderator).status_code == 404
    )
    assert (
        client.delete(f"/api/hw7/trials/{trial_id}", headers=moderator).status_code
        == 404
    )


def test_every_role_can_list_and_read(client):
    """List and read return 200 for all three roles, and 401 without a token."""
    writer = login(client, "writer_user")
    trial_id = client.post("/api/hw7/trials", json=TRIAL, headers=writer).json()["id"]
    for username in ("reader_user", "writer_user", "moderator_user"):
        headers = login(client, username)
        assert client.get("/api/hw7/trials", headers=headers).status_code == 200
        assert (
            client.get(f"/api/hw7/trials/{trial_id}", headers=headers).status_code
            == 200
        )
    assert client.get("/api/hw7/trials").status_code == 401


def test_server_url_drops_database_but_keeps_login():
    """The server-level URL has no database name but keeps user, password and host."""
    url = make_url("mysql+pymysql://root:p%40ss@localhost:3306/s4833_hw7")
    result = init_hw7_db.server_url(url)
    assert result.database is None
    assert (result.username, result.password) == ("root", "p@ss")
    assert (result.host, result.port) == ("localhost", 3306)
