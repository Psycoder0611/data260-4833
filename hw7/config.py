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

# Local model (Ollama, same as HW1/HW6) and agent-loop limits
MODEL_NAME = os.getenv("HW7_MODEL", "qwen3:8b")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_REPLY_TOKENS = int(os.getenv("HW7_MAX_REPLY_TOKENS", "600"))
TEMPERATURE = float(os.getenv("HW7_TEMPERATURE", "0.0"))
MAX_ITERATIONS = 8  # hard ceiling on model turns per run
MAX_FAILED_REPAIRS = 2  # stop cleanly after this many failed repairs

RAW_DIR = REPO_ROOT / "reports" / "hw07" / "raw"
TOOL_LOG_PATH = RAW_DIR / "tool_invocations.jsonl"
