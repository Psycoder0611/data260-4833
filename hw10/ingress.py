# ruff: noqa: E501
"""Traced request path: semantic cache first, Kafka pipeline on a miss.

    ask(question)
      cache_lookup span (embed + vector search, hit or miss)
      hit  -> answer from the cache, request span, done
      miss -> publish {correlation_id, question} to s4833_inbox
              Planner -> s4833_tasks -> Writer -> s4833_drafts -> Reviewer -> s4833_final
              wait for the final message (or a dead letter)
              store an approved answer in the cache (same rule as HW9)

trace_id == correlation_id == the id carried by every Kafka message of the request.
Spans of the agents come from hw10.kafka_trace; this module writes cache_lookup,
queue_final (final message -> received here) and request.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, Optional

from hw8 import config as hw8_config
from hw8 import kafka_io
from hw9 import facts

from hw10 import config, tracing
from hw10.collector import Collector, bundle_for, save_bundle
from hw10.kafka_trace import FAULT_FIELD

COMPONENT = "INGRESS"


class TracedIngress:
    """One ingress object serves requests one after another."""

    def __init__(
        self,
        cache: Any,
        engine: Any = None,
        threshold: float = config.CACHE_THRESHOLD,
        bootstrap: Optional[str] = None,
        timeout: float = config.REQUEST_TIMEOUT_SECONDS,
        span_path=None,
        check_version: bool = True,
    ) -> None:
        """Wire the cache (real or in-memory), the database engine and Kafka."""
        self.cache = cache
        self.engine = engine
        self.threshold = threshold
        self.bootstrap = bootstrap
        self.timeout = timeout
        self.span_path = span_path
        self.check_version = check_version
        self.collector = Collector(bootstrap)
        self.producer: Any = None

    async def start(self) -> None:
        """Connect the producer and the collector (positioned at the end of the topics)."""
        from hw8.rpc_client import start_with_retry

        self.producer = kafka_io.make_producer(self.bootstrap)
        await start_with_retry(self.producer, "producer")
        await self.collector.start(from_beginning=False)

    async def stop(self) -> None:
        """Disconnect."""
        await self.collector.stop()
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None

    def _emit(self, trace_id, stage, start, end, status="ok", error=None, attrs=None):
        """Write one ingress span."""
        return tracing.record(
            trace_id, stage, start, end, status, error, COMPONENT, attrs, self.span_path
        )

    async def ask(
        self,
        question: str,
        trace_id: Optional[str] = None,
        fault: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Answer one question; always writes a request span, also on failure."""
        trace_id = trace_id or str(uuid.uuid4())
        t_request = time.time()
        result: Dict[str, Any] = {
            "trace_id": trace_id,
            "question": question,
            "path": "miss",
            "status": "ok",
            "error": None,
            "answer": None,
            "similarity": 0.0,
            "bundle": None,
        }
        try:
            await self._ask(question, trace_id, fault, result)
        except Exception as exc:  # the caller gets the failure; the trace shows it
            result["status"] = "error"
            result["error"] = f"{type(exc).__name__}: {exc}"
        t_end = time.time()
        result["latency_ms"] = round((t_end - t_request) * 1000, 1)
        self._emit(
            trace_id,
            tracing.REQUEST,
            t_request,
            t_end,
            result["status"],
            result["error"],
            {"path": result["path"], "similarity": result["similarity"]},
        )
        return result

    async def _ask(self, question, trace_id, fault, result) -> None:
        """The cache lookup and, on a miss, the Kafka round trip."""
        t0 = time.time()
        vector = await asyncio.to_thread(self.cache.embed, question)
        hit = await asyncio.to_thread(self.cache.lookup, question, vector)
        similarity = hit.similarity if hit else 0.0
        is_hit = bool(hit and similarity >= self.threshold)
        stale = False
        if is_hit and self.check_version and self.engine is not None:
            current = facts.current_version(self.engine, hit.entity)
            if current != hit.data_version:
                await asyncio.to_thread(self.cache.delete, hit.key)
                is_hit, stale = False, True
        self._emit(
            trace_id,
            tracing.CACHE_LOOKUP,
            t0,
            time.time(),
            attrs={
                "cache_hit": is_hit,
                "similarity": similarity,
                "threshold": self.threshold,
                "stale_invalidated": stale,
                "matched_query": hit.query if hit else None,
            },
        )
        result["similarity"] = similarity
        if is_hit:
            result["path"] = "hit"
            result["answer"] = hit.answer
            return

        facts_text, version, entity = facts.facts_for(self.engine, question)
        text = question
        if facts_text:
            text = (
                f"{question}\n\nFacts from the listings database (use them exactly):\n"
                f"{facts_text}"
            )
        message: Dict[str, Any] = {"correlation_id": trace_id, "question": text}
        if fault:
            message[FAULT_FIELD] = fault
        await self.producer.send_and_wait(
            config.INBOX_TOPIC,
            kafka_io.dumps(message),
            key=trace_id.encode("utf-8"),
        )
        entry = await self.collector.wait_for(trace_id, self.timeout)
        received = time.time()
        bundle = bundle_for(trace_id, entry)
        result["bundle"] = bundle
        save_bundle(bundle)
        final = entry.get("final")
        if final is not None:
            stamp = final.get("timestamp_ms")
            if stamp:
                self._emit(
                    trace_id,
                    tracing.QUEUE_FINAL,
                    stamp / 1000.0,
                    received,
                    attrs={"partition": final["partition"], "offset": final["offset"]},
                )
        if entry.get("timed_out"):
            raise TimeoutError(
                f"no final answer or dead letter within {self.timeout:.0f}s"
            )
        if final is None:
            dead = entry["dead_letter"]["value"]
            raise RuntimeError(
                f"request dead-lettered at stage {dead.get('failed_stage')}: {dead.get('error')}"
            )
        value = final["value"]
        result["answer"] = value.get("answer")
        result["review_status"] = value.get("status")
        result["review_score"] = value.get("score")
        if value.get("status") == "approved" and result["answer"]:
            await asyncio.to_thread(
                self.cache.store,
                question,
                result["answer"],
                version,
                vector,
                entity,
            )


__all__ = ["TracedIngress", "hw8_config"]
