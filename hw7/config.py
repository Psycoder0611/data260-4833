"""Central settings for HW7. Values come from the environment (.env) with defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed personal configuration (never recalculated)
HOMEWORK = 7
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
DOMAIN_ID = 1

# Separate MySQL database for the HW7 users table. It reuses the host, user and
# password from DATABASE_URL (HW4/HW5) and only swaps the database name, so the
# HW4 users table in s4833_rel is never touched.
HW7_DB_NAME = f"{PREFIX}_hw7"
_BASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root@localhost/s4833_rel")
HW7_DATABASE_URL = os.getenv("HW7_DATABASE_URL") or make_url(_BASE_URL).set(
    database=HW7_DB_NAME
).render_as_string(hide_password=False)

# JWT settings. The key is read from the environment; the default is for local
# development only.
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "dev-only-hw7-jwt-secret-key-change-me-4833"
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

ROLES = ("reader", "writer", "moderator")

# Demo accounts created by init_hw7_db.py (local homework use only).
DEMO_USERS = (
    ("reader_user", "Reader#4833", "reader"),
    ("writer_user", "Writer#4833", "writer"),
    ("moderator_user", "Moderator#4833", "moderator"),
)
