# ruff: noqa: E501
"""Domain Q&A endpoint with a semantic cache at the ingress (Part 2 and 3.5).

    answer(query):
      embed -> vector search in Redis
        similarity >= threshold  -> return the stored answer (is_cached = True)
        otherwise                -> run the HW8 agents, store the answer, return it

With check_version=True a hit is only served if the data-version marker stored with
the answer still matches the database (invalidation strategy of 3.5).
"""

import time
from typing import Any, Dict

from hw9 import config, facts
from hw9.logs import get_logger


class QAService:
    """Cache in front of the HW8 agent pipeline."""

    def __init__(
        self,
        cache,
        agents,
        engine=None,
        threshold: float = config.DEFAULT_THRESHOLD,
        check_version: bool = False,
    ) -> None:
        """Wire the cache, the agent backend and the database engine together."""
        self.cache = cache
        self.agents = agents
        self.engine = engine
        self.threshold = threshold
        self.check_version = check_version
        self.log = get_logger("CACHE")
        self.stats = {"queries": 0, "hits": 0, "misses": 0, "invalidated": 0}

    def answer(self, query: str) -> Dict[str, Any]:
        """Answer one query; returns the answer plus is_cached, similarity and timings."""
        t_start = time.perf_counter()
        self.stats["queries"] += 1
        vector = self.cache.embed(query)
        hit = self.cache.lookup(query, embedding=vector)
        t_lookup = time.perf_counter()
        lookup_ms = round((t_lookup - t_start) * 1000, 1)
        similarity = hit.similarity if hit else 0.0
        invalidated = False

        if hit and similarity >= self.threshold:
            fresh = True
            if self.check_version and self.engine is not None:
                current = facts.current_version(self.engine, hit.entity)
                fresh = current == hit.data_version
                if not fresh:
                    self.log.info(
                        "STALE   similarity=%.3f cached_version=%s current_version=%s "
                        "-> invalidating entry and recomputing",
                        similarity, hit.data_version, current,
                    )  # fmt: skip
                    self.cache.delete(hit.key)
                    self.stats["invalidated"] += 1
                    invalidated = True
            if fresh:
                latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
                self.stats["hits"] += 1
                self.log.info(
                    "HIT     similarity=%.3f threshold=%.2f latency=%.1fms query=%r matched=%r",
                    similarity, self.threshold, latency_ms, query, hit.query,
                )  # fmt: skip
                return {
                    "query": query,
                    "answer": hit.answer,
                    "is_cached": True,
                    "similarity": similarity,
                    "latency_ms": latency_ms,
                    "lookup_ms": lookup_ms,
                    "matched_query": hit.query,
                    "data_version": hit.data_version,
                    "invalidated": False,
                }

        if not invalidated:
            self.log.info(
                "MISS    best_similarity=%.3f threshold=%.2f query=%r",
                similarity, self.threshold, query,
            )  # fmt: skip
        facts_text, version, entity = facts.facts_for(self.engine, query)
        run = self.agents.run(query, facts_text)
        if run["status"] == "approved":
            self.cache.store(
                query,
                run["answer"],
                data_version=version,
                embedding=vector,
                entity=entity,
            )
        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
        self.stats["misses"] += 1
        self.log.info(
            "AGENT   status=%s score=%s agent=%.1fms total=%.1fms",
            run["status"], run["score"], run["agent_ms"], latency_ms,
        )  # fmt: skip
        return {
            "query": query,
            "answer": run["answer"],
            "is_cached": False,
            "similarity": similarity,
            "latency_ms": latency_ms,
            "lookup_ms": lookup_ms,
            "agent_ms": run["agent_ms"],
            "status": run["status"],
            "data_version": version,
            "invalidated": invalidated,
        }

    def hit_rate(self) -> float:
        """Percentage of queries served from the cache."""
        total = self.stats["queries"]
        return round(100 * self.stats["hits"] / total, 1) if total else 0.0
