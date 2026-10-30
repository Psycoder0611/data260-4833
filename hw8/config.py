"""Central settings for HW8. Values come from the environment with defaults.

The personal configuration (SID4, port, prefix, seeds, domain) is fixed for the
whole semester and is never recalculated.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed personal configuration
HOMEWORK = 8
STUDENT_NAME = "Trapti Kulshrestha"
SID4 = 4833
PORT_BASE = 8333  # 8000 + (4833 mod 900)
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833  # 260000 + SID4 (HW8 formula)
DOMAIN_ID = 1  # 4833 mod 8 -> Clinical Trial Listings
DOMAIN_NAME = "Clinical Trial Listings"

# Entity naming. The spec says to replace ENTITY with the real entity name, so
# CREATE_ENTITY becomes CREATE_CLINICAL_TRIAL and entity_id becomes
# clinical_trial_id. Change only these three lines to rename them.
ENTITY_NAME = "CLINICAL_TRIAL"
CREATE_OPERATION = f"CREATE_{ENTITY_NAME}"
GET_OPERATION = f"GET_{ENTITY_NAME}"
ID_FIELD = "clinical_trial_id"
GENERIC_ID_FIELD = "entity_id"  # also returned, so the generic spec wording matches

# Kafka. Host scripts use localhost:9092; containers use kafka:19092.
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Part 1 topics (exactly two)
REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"

# Part 2 / 3 topics
INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"
DEAD_LETTER_TOPIC = f"{PREFIX}_dead_letter"

TOPIC_PARTITIONS = {
    REQUEST_TOPIC: 1,
    RESPONSE_TOPIC: 1,
    INBOX_TOPIC: 1,
    TASKS_TOPIC: 2,  # two partitions are needed for the ordering test
    DRAFTS_TOPIC: 1,
    FINAL_TOPIC: 1,
    DEAD_LETTER_TOPIC: 1,
}

# Consumer groups
WORKER_GROUP = f"{PREFIX}_entity_worker"
PLANNER_GROUP = f"{PREFIX}_planner"
WRITER_GROUP = f"{PREFIX}_writers"
REVIEWER_GROUP = f"{PREFIX}_reviewer"

RPC_TIMEOUT_SECONDS = float(os.getenv("HW8_RPC_TIMEOUT", "8"))

# Local model (Ollama, same as HW1/HW6/HW7)
MODEL_NAME = os.getenv("HW8_MODEL", "qwen3:8b")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_REPLY_TOKENS = int(os.getenv("HW8_MAX_REPLY_TOKENS", "400"))
TEMPERATURE = float(os.getenv("HW8_TEMPERATURE", "0.0"))
LLM_MODE = os.getenv("HW8_LLM_MODE", "ollama")  # "ollama" or "stub"

# Failure handling
MAX_ATTEMPTS = int(os.getenv("HW8_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("HW8_RETRY_BACKOFF", "0.5"))
APPROVAL_MIN_SCORE = 6  # reviewer score (1-10) needed for status "approved"

# Output folders
REPORT_DIR = Path(os.getenv("HW8_REPORT_DIR", str(REPO_ROOT / "reports" / "hw08")))
RAW_DIR = REPORT_DIR / "raw"
STATE_DIR = Path(os.getenv("HW8_STATE_DIR", str(REPORT_DIR / "state")))
RUN_LOG_PATH = REPORT_DIR / "RUN_LOG.txt"
WORKER_TRACE_PATH = RAW_DIR / "worker_trace.jsonl"
IDEMPOTENCY_DB_PATH = STATE_DIR / "idempotency.db"

# When "0", the API and RPC client print only start-up and error lines. Used for the
# JMeter runs so console output does not distort the timings.
API_VERBOSE = os.getenv("HW8_API_VERBOSE", "1") != "0"
TRACE_ENABLED = os.getenv("HW8_TRACE", "0") == "1"
