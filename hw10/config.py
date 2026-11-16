# ruff: noqa: E501
"""Central settings for HW10. Values come from the environment with defaults.

The personal configuration (SID4, port, prefix, seeds, domain) is fixed for the
whole semester and is never recalculated. HW10 adds no new Kafka topic and no new
ID: the HW8 correlation_id is used as the trace_id everywhere.
"""

import os
from pathlib import Path

from hw8 import config as hw8_config

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed personal configuration
HOMEWORK = 10
STUDENT_NAME = "Trapti Kulshrestha"
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
DOMAIN_ID = 1
DOMAIN_NAME = "Clinical Trial Listings"

# Kafka topics are the HW8 topics, unchanged.
INBOX_TOPIC = hw8_config.INBOX_TOPIC
TASKS_TOPIC = hw8_config.TASKS_TOPIC
DRAFTS_TOPIC = hw8_config.DRAFTS_TOPIC
FINAL_TOPIC = hw8_config.FINAL_TOPIC
DEAD_LETTER_TOPIC = hw8_config.DEAD_LETTER_TOPIC

# HW10 consumer groups (separate from the HW8 groups so old messages are not replayed)
PLANNER_GROUP = f"{PREFIX}_hw10_planner"
WRITER_GROUP = f"{PREFIX}_hw10_writers"
REVIEWER_GROUP = f"{PREFIX}_hw10_reviewer"

# Ingress / request handling
REQUEST_TIMEOUT_SECONDS = float(os.getenv("HW10_REQUEST_TIMEOUT", "240"))
CACHE_THRESHOLD = float(os.getenv("HW10_CACHE_THRESHOLD", "0.85"))

# Judge (local model through Ollama, never a hosted API)
JUDGE_MODEL = os.getenv("HW10_JUDGE_MODEL", "qwen3:8b")
JUDGE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
JUDGE_TEMPERATURE = 0.0
JUDGE_SEED = SEED
JUDGE_MAX_TOKENS = int(os.getenv("HW10_JUDGE_MAX_TOKENS", "500"))
JUDGE_CALL_TIMEOUT = float(os.getenv("HW10_JUDGE_CALL_TIMEOUT", "90"))  # one HTTP call
METRIC_TIMEOUT = float(os.getenv("HW10_METRIC_TIMEOUT", "240"))  # one whole metric
SCORE_MIN, SCORE_MAX = 1, 5

# Folders and files
DATA_DIR = REPO_ROOT / "data" / "hw10"
CASES_PATH = DATA_DIR / "eval_cases.json"
LABELS_PATH = DATA_DIR / "human_labels.csv"
QUESTIONS_PATH = DATA_DIR / "latency_questions.json"
REPORT_DIR = Path(os.getenv("HW10_REPORT_DIR", str(REPO_ROOT / "reports" / "hw10")))
RAW_DIR = REPORT_DIR / "raw"
JOINED_DIR = RAW_DIR / "joined"
STATE_DIR = REPORT_DIR / "state"
SPANS_PATH = Path(os.getenv("HW10_SPAN_PATH", str(RAW_DIR / "spans.jsonl")))
RUN_LOG_PATH = REPORT_DIR / "RUN_LOG.txt"
IDEMPOTENCY_DB_PATH = STATE_DIR / "idempotency.db"
