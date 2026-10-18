"""Central settings for HW6. Values come from the environment (.env) with safe defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed personal configuration (never recalculated)
HOMEWORK = 6
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
DOMAIN_ID = 1

# MongoDB (local Docker container, no password needed on localhost)
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", f"{PREFIX}_doc")
TRIALS_COLLECTION = "clinical_trials"
MESSAGES_COLLECTION = "messages"
SUMMARIES_COLLECTION = "summaries"
EPISODES_COLLECTION = "episodes"

# Local models (Ollama)
MODEL_NAME = os.getenv("HW6_MODEL", "qwen3:8b")
EMBEDDING_MODEL = os.getenv("HW6_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_REPLY_TOKENS = int(os.getenv("HW6_MAX_REPLY_TOKENS", "400"))

# Memory constants (Part 2 defaults, Part 3 overrides them per request)
SHORT_TERM_N = int(os.getenv("SHORT_TERM_N", "12"))
SUMMARIZE_EVERY_USER_MSGS = int(os.getenv("SUMMARIZE_EVERY_USER_MSGS", "5"))
EPISODIC_TOP_K = int(os.getenv("EPISODIC_TOP_K", "3"))
LIFETIME_EVERY_SESSION_SUMMARIES = int(os.getenv("LIFETIME_EVERY_SESSION_SUMMARIES", "3"))
KEEP_RECENT_VERBATIM = int(os.getenv("KEEP_RECENT_VERBATIM", "6"))

# Part 4 file-based memory
AGENT_FILE = REPO_ROOT / "AGENT.md"
MEMORY_FILE = REPO_ROOT / "MEMORY.md"
RECENT_CONVERSATION_FILE = REPO_ROOT / "data" / "hw6_recent_conversation.jsonl"
CONSOLIDATION_LINE_LIMIT = 40
CONSOLIDATION_MAX_AGE_HOURS = 24
