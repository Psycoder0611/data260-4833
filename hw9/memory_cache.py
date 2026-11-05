"""Pure-Python stand-in for SemanticCache, used only by the offline tests.

Same methods as hw9.semantic_cache.SemanticCache, but entries live in a list and
cosine similarity is computed with numpy. It lets the cache logic (hit, miss, stale
check, invalidation) be tested without Redis Stack. Reported results always come
from the real Redis vector index.
"""

import hashlib
from typing import Dict, List, Optional

import numpy as np

from hw9.semantic_cache import CacheHit


class MemorySemanticCache:
    """Same interface as SemanticCache, without Redis."""

    def __init__(self, embedder) -> None:
        """Start with an empty cache."""
        self.embedder = embedder
        self.entries: Dict[str, dict] = {}

    def ensure_index(self) -> None:
        """Nothing to create."""

    def embed(self, query: str) -> List[float]:
        """Embed a query."""
        return self.embedder.embed(query)

    def lookup(
        self, query: str, embedding: Optional[List[float]] = None
    ) -> Optional[CacheHit]:
        """Best match by cosine similarity, or None if empty."""
        if not self.entries:
            return None
        vector = np.asarray(embedding if embedding is not None else self.embed(query))
        best_key, best_sim = None, -2.0
        for key, entry in self.entries.items():
            sim = float(np.dot(vector, entry["embedding"]))
            if sim > best_sim:
                best_key, best_sim = key, sim
        entry = self.entries[best_key]
        return CacheHit(
            key=best_key,
            query=entry["query"],
            answer=entry["answer"],
            data_version=entry["data_version"],
            similarity=round(best_sim, 4),
            entry_id=best_key,
            entity=entry["entity"],
        )

    def store(
        self, query, answer, data_version="static", embedding=None, entity="none"
    ) -> str:
        """Add or replace one entry."""
        vector = embedding if embedding is not None else self.embed(query)
        key = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:12]
        self.entries[key] = {
            "query": query,
            "answer": answer,
            "data_version": data_version,
            "entity": entity,
            "embedding": np.asarray(vector),
        }
        return key

    def delete(self, key: str) -> None:
        """Remove one entry."""
        self.entries.pop(key, None)

    def clear(self) -> int:
        """Remove everything."""
        count = len(self.entries)
        self.entries.clear()
        return count

    def size(self) -> int:
        """Number of entries."""
        return len(self.entries)
