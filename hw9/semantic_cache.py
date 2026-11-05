"""Semantic response cache stored in Redis with a vector index (RediSearch).

Each entry is a Redis hash under s4833:semcache:<id> with the query text, its
embedding (FLOAT32 vector), the final answer and a data-version marker. The index
s4833:idx:semcache compares embeddings with cosine distance; similarity is
1 - distance. FLAT (exact) search is used: the cache is small, so there is no need
for an approximate index.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

from hw9 import config


@dataclass
class CacheHit:
    """The best match found by a lookup."""

    key: str
    query: str
    answer: str
    data_version: str
    similarity: float
    entry_id: str
    entity: str = "none"


def _as_bytes(vector: List[float]) -> bytes:
    """Pack an embedding as float32 bytes for Redis."""
    return np.asarray(vector, dtype=np.float32).tobytes()


def _text(value: Any) -> str:
    """Redis may return bytes; always give back str."""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class SemanticCache:
    """Lookup and store of answers by meaning, not by exact text."""

    def __init__(self, redis_client, embedder, dim: Optional[int] = None) -> None:
        """redis_client must be created with decode_responses=False (binary vectors)."""
        self.r = redis_client
        self.embedder = embedder
        self.dim = dim or getattr(embedder, "dim", config.EMBED_DIM)

    # ------------------------------------------------------------------ index
    def ensure_index(self) -> None:
        """Create the vector index if it does not exist yet."""
        try:
            self.r.ft(config.CACHE_INDEX).info()
            return
        except ResponseError:
            pass
        schema = (
            TextField("query"),
            TextField("answer"),
            TagField("data_version"),
            TagField("entity"),
            VectorField(
                "embedding",
                "FLAT",
                {"TYPE": "FLOAT32", "DIM": self.dim, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        self.r.ft(config.CACHE_INDEX).create_index(
            schema,
            definition=IndexDefinition(
                prefix=[config.CACHE_KEY_PREFIX], index_type=IndexType.HASH
            ),
        )

    def clear(self) -> int:
        """Delete every cache entry (keys with the s4833:semcache: prefix)."""
        keys = list(self.r.scan_iter(match=f"{config.CACHE_KEY_PREFIX}*"))
        return int(self.r.delete(*keys)) if keys else 0

    def drop_index(self) -> None:
        """Remove the index (entries stay until clear())."""
        try:
            self.r.ft(config.CACHE_INDEX).dropindex(delete_documents=False)
        except ResponseError:
            pass

    def size(self) -> int:
        """Number of stored entries."""
        return sum(1 for _ in self.r.scan_iter(match=f"{config.CACHE_KEY_PREFIX}*"))

    # ------------------------------------------------------------------ lookup
    def embed(self, query: str) -> List[float]:
        """Embed a query with the cache's embedder."""
        return self.embedder.embed(query)

    def lookup(
        self, query: str, embedding: Optional[List[float]] = None
    ) -> Optional[CacheHit]:
        """Return the most similar stored query, or None if the cache is empty.

        The caller compares hit.similarity with its threshold; the best match is
        returned even when it is below the threshold so it can be logged.
        """
        vector = embedding if embedding is not None else self.embed(query)
        q = (
            Query("*=>[KNN 1 @embedding $vec AS dist]")
            .sort_by("dist")
            .return_fields("query", "answer", "data_version", "entity", "dist")
            .dialect(2)
        )
        result = self.r.ft(config.CACHE_INDEX).search(
            q, query_params={"vec": _as_bytes(vector)}
        )
        if not result.docs:
            return None
        doc = result.docs[0]
        return CacheHit(
            key=_text(doc.id),
            query=_text(doc.query),
            answer=_text(doc.answer),
            data_version=_text(doc.data_version),
            similarity=round(1.0 - float(doc.dist), 4),
            entry_id=_text(doc.id).rsplit(":", 1)[-1],
            entity=_text(getattr(doc, "entity", "none")),
        )

    # ------------------------------------------------------------------- store
    def store(
        self,
        query: str,
        answer: str,
        data_version: str = "static",
        embedding: Optional[List[float]] = None,
        entity: str = "none",
    ) -> str:
        """Store one answer with its query, embedding and data-version marker."""
        vector = embedding if embedding is not None else self.embed(query)
        entry_id = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:12]
        key = f"{config.CACHE_KEY_PREFIX}{entry_id}"
        self.r.hset(
            key,
            mapping={
                "query": query,
                "answer": answer,
                "data_version": data_version,
                "entity": entity,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "embedding": _as_bytes(vector),
            },
        )
        return key

    def delete(self, key: str) -> None:
        """Remove one entry (used by invalidation)."""
        self.r.delete(key)

    def describe(self) -> Dict[str, Any]:
        """Small status dictionary for logs."""
        return {"index": config.CACHE_INDEX, "entries": self.size(), "dim": self.dim}
