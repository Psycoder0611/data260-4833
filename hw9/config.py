"""Central settings for HW9. Values come from the environment with defaults.

The personal configuration (SID4, port, prefix, seeds, domain) is fixed for the
whole semester and is never recalculated. Every Redis key and index name starts
with PREFIX.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed personal configuration
HOMEWORK = 9
STUDENT_NAME = "Trapti Kulshrestha"
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
DOMAIN_ID = 1
DOMAIN_NAME = "Clinical Trial Listings"

# Redis (Redis Stack, so the vector index module is available)
REDIS_HOST = os.getenv("HW9_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("HW9_REDIS_PORT", "6379"))

# Part 1: view counter
ENTITY_NAME = "clinical_trial"
VIEWS_KEY_FORMAT = PREFIX + ":views:" + ENTITY_NAME + ":{id}"
SYNC_EVERY = 10
TRIALS_TABLE = "clinical_trials"
VIEWS_COLUMN = "view_count"

# Part 2/3: semantic cache
CACHE_KEY_PREFIX = f"{PREFIX}:semcache:"
CACHE_INDEX = f"{PREFIX}:idx:semcache"
DEFAULT_THRESHOLD = 0.85
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
EMBED_MODEL = os.getenv("HW9_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Local model for the miss path and for Part 4 (same adapter as HW1 to HW8)
MODEL_NAME = os.getenv("HW9_MODEL", "qwen3:8b")
LLM_MODE = os.getenv("HW9_LLM_MODE", "ollama")  # "ollama" or "stub"

# Cost model for 3.4 (all amounts in US dollars, assumptions explained in the report)
COST_MISS = 0.02  # one agent run: three model calls worth of tokens plus the wait
COST_FALSE_HIT = 2.00  # a wrong listing answer reaches a user and needs human follow-up

# Data and output folders
DATA_DIR = REPO_ROOT / "data" / "hw09"
REPORT_DIR = Path(os.getenv("HW9_REPORT_DIR", str(REPO_ROOT / "reports" / "hw09")))
RAW_DIR = REPORT_DIR / "raw"
CASES_PATH = REPO_ROOT / "cache_cases.yaml"
RUN_LOG_PATH = REPORT_DIR / "RUN_LOG.txt"


def database_url() -> str:
    """Database URL from DATABASE_URL (same variable as database.py); never printed."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return os.getenv("DATABASE_URL", "mysql+pymysql://root@localhost/s4833_rel")
