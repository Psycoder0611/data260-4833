"""HW7 Part 1 demo calls (for screenshots).

Usage: python demo_hw07_part1.py login | me | badtoken | create | delete | list | all

Needs the app running on port 8333 (python main.py), the local MySQL server and
the users table from init_hw7_db.py. Each command is independent and cleans up
the demo trials it makes.
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import jwt
import requests

from database import db_session_basede26
from hw7 import config
from models import ResearchOrganizationDB

BASE = f"http://127.0.0.1:{config.PORT_BASE}"
BANNER = "Student: Trapti Kulshrestha | SID4 4833 | HW7 Part 1 demo"
PASSWORDS = {username: password for username, password, _ in config.DEMO_USERS}


def show(title: str, response: requests.Response) -> requests.Response:
    """Print one request result with its HTTP status."""
    print(f"\n--- {title} -> HTTP {response.status_code}")
    if response.text:
        try:
            print(json.dumps(response.json(), indent=2))
        except ValueError:
            print(response.text)
    return response


def login(username: str, password: str = "") -> requests.Response:
    """POST /auth/login for a demo user (password defaults to the demo one)."""
    return requests.post(
        f"{BASE}/auth/login",
        data={"username": username, "password": password or PASSWORDS[username]},
        timeout=10,
    )


def auth(username: str) -> dict:
    """Log in quietly and return the Authorization header."""
    token = login(username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def first_org_id() -> int:
    """Return the id of an existing research organization (from HW5 data)."""
    with db_session_basede26() as session:
        org = (
            session.query(ResearchOrganizationDB)
            .order_by(ResearchOrganizationDB.id)
            .first()
        )
    if org is None:
        sys.exit("No research organization found. Seed the HW5 data first.")
    return org.id


def trial_body() -> dict:
    """Return a unique demo trial body."""
    stamp = datetime.now().strftime("%H%M%S%f")
    return {
        "trialTitle": "HW7 JWT Demo Trial",
        "trial_code": f"HW7-DEMO-{stamp}",
        "participant_capacity": 25,
        "organization_id": first_org_id(),
    }


def cleanup(trial_id: int) -> None:
    """Remove a demo trial with the moderator token (not shown on screen)."""
    requests.delete(
        f"{BASE}/api/hw7/trials/{trial_id}", headers=auth("moderator_user"), timeout=10
    )


def part_login() -> None:
    """Valid login returns a JWT; a wrong password returns 401."""
    show("POST /auth/login (writer_user, correct password)", login("writer_user"))
    show(
        "POST /auth/login (writer_user, wrong password)",
        login("writer_user", "wrong-password"),
    )


def part_me() -> None:
    """/auth/me with no token returns 401."""
    show("GET /auth/me (no token)", requests.get(f"{BASE}/auth/me", timeout=10))


def part_badtoken() -> None:
    """/auth/me with an invalid token and an expired token returns 401."""
    show(
        "GET /auth/me (invalid token 'abc.def.ghi')",
        requests.get(
            f"{BASE}/auth/me",
            headers={"Authorization": "Bearer abc.def.ghi"},
            timeout=10,
        ),
    )
    expired = jwt.encode(
        {
            "sub": "writer_user",
            "role": "writer",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )
    print("(expired token = signed with the real key, exp set 5 minutes in the past)")
    show(
        "GET /auth/me (expired token)",
        requests.get(
            f"{BASE}/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
            timeout=10,
        ),
    )
    show(
        "GET /auth/me (valid reader token, for comparison)",
        requests.get(f"{BASE}/auth/me", headers=auth("reader_user"), timeout=10),
    )


def part_create() -> None:
    """reader gets 403 on create; writer gets 201."""
    show(
        "POST /api/hw7/trials (reader_user)",
        requests.post(
            f"{BASE}/api/hw7/trials",
            json=trial_body(),
            headers=auth("reader_user"),
            timeout=10,
        ),
    )
    created = show(
        "POST /api/hw7/trials (writer_user)",
        requests.post(
            f"{BASE}/api/hw7/trials",
            json=trial_body(),
            headers=auth("writer_user"),
            timeout=10,
        ),
    )
    if created.status_code == 201:
        cleanup(created.json()["id"])
        print("\n(demo trial removed again by moderator_user)")


def part_delete() -> None:
    """writer gets 403 on delete; moderator gets 200."""
    made = requests.post(
        f"{BASE}/api/hw7/trials",
        json=trial_body(),
        headers=auth("writer_user"),
        timeout=10,
    )
    trial_id = made.json()["id"]
    print(f"(setup: writer_user created demo trial id {trial_id})")
    show(
        f"DELETE /api/hw7/trials/{trial_id} (writer_user)",
        requests.delete(
            f"{BASE}/api/hw7/trials/{trial_id}", headers=auth("writer_user"), timeout=10
        ),
    )
    show(
        f"DELETE /api/hw7/trials/{trial_id} (moderator_user)",
        requests.delete(
            f"{BASE}/api/hw7/trials/{trial_id}",
            headers=auth("moderator_user"),
            timeout=10,
        ),
    )
    show(
        f"GET /api/hw7/trials/{trial_id} (after delete)",
        requests.get(
            f"{BASE}/api/hw7/trials/{trial_id}", headers=auth("reader_user"), timeout=10
        ),
    )


def part_list() -> None:
    """A reader token can list trials (200)."""
    show(
        "GET /api/hw7/trials?limit=3 (reader_user)",
        requests.get(
            f"{BASE}/api/hw7/trials?limit=3", headers=auth("reader_user"), timeout=10
        ),
    )


PARTS = {
    "login": part_login,
    "me": part_me,
    "badtoken": part_badtoken,
    "create": part_create,
    "delete": part_delete,
    "list": part_list,
}


def main() -> None:
    """Run the chosen demo part (or all of them)."""
    choice = sys.argv[1] if len(sys.argv) > 1 else "all"
    if choice != "all" and choice not in PARTS:
        sys.exit(__doc__)
    print(BANNER)
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    for name, function in PARTS.items():
        if choice in ("all", name):
            function()


if __name__ == "__main__":
    main()
