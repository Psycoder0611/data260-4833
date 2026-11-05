"""Builds the real objects (Redis, embedder, agents, database) for the run scripts."""

from typing import Tuple

import redis

from hw9 import config, db
from hw9.agent_backend import HW8Agents
from hw9.embedder import OllamaEmbedder
from hw9.semantic_cache import SemanticCache


def make_binary_redis() -> "redis.Redis":
    """Redis client for the semantic cache (binary vectors, so no decode_responses)."""
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT)
    client.ping()
    return client


def make_cache() -> SemanticCache:
    """SemanticCache on real Redis Stack with the real embedder; creates the index."""
    cache = SemanticCache(make_binary_redis(), OllamaEmbedder())
    cache.ensure_index()
    return cache


def make_everything() -> Tuple[SemanticCache, HW8Agents, object]:
    """Return (cache, agents, database engine)."""
    return make_cache(), HW8Agents(), db.make_engine()
