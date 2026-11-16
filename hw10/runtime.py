"""Builds the real objects for the HW10 run scripts (Redis cache, database, judge)."""

from typing import Any, Optional

from hw9 import db
from hw9 import config as hw9_config
from hw9.runtime import make_cache as make_hw9_cache

from hw10.judge import OllamaJudge


def make_engine() -> Optional[Any]:
    """MySQL engine for the listings facts, or None if the database is not reachable."""
    try:
        engine = db.make_engine()
        with engine.connect():
            pass
        return engine
    except Exception as exc:  # the run still works, only without trial facts
        print(f"WARNING: database not reachable ({type(exc).__name__}); questions run without listing facts")
        return None


def make_judge() -> OllamaJudge:
    """Local judge (Ollama qwen3:8b)."""
    return OllamaJudge()


def make_cache():
    """Semantic cache in its own HW10 namespace (all names still start with s4833).

    The HW9 cache already holds the answers of the HW9 experiments, and the embedding model
    rates questions that differ only in the trial code as very similar, so many new
    questions would be served from those old entries. HW10 therefore uses a separate key
    prefix and index; the HW9 entries are left untouched.
    """
    hw9_config.CACHE_KEY_PREFIX = f"{hw9_config.PREFIX}:hw10:semcache:"
    hw9_config.CACHE_INDEX = f"{hw9_config.PREFIX}:idx:hw10cache"
    return make_hw9_cache()


__all__ = ["make_cache", "make_engine", "make_judge"]
