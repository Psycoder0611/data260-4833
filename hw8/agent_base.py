"""Generic Kafka agent loop used by Planner, Writer and Reviewer (Parts 2 and 3).

One AgentRunner reads one topic, hands each message to a handler, publishes the
handler's result to the next topic, and commits the offset. The failure
behaviour is set by options so the "before fix" and "after fix" runs of Part 3
use the same code:

  idempotent     skip a message whose (agent, correlation_id) is already done
  commit_mode    "after"      commit only after the result is published (fix)
                 "on_receive" commit as soon as the message arrives (before)
  max_attempts   3 = bounded retries; 0 = retry forever (before)
  dead_letter    True = send the exhausted message to <PREFIX>_dead_letter (fix)
                 False = stop with an error (the message would be redelivered)
  key_mode       key of the published message: "correlation", "entity" or "none"
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aiokafka import TopicPartition

from hw8 import config, kafka_io
from hw8.idempotency import IdempotencyStore
from hw8.logs import get_logger
from hw8.pipeline import Handler
from hw8.rpc_client import start_with_retry


class RetriesExhausted(Exception):
    """Raised (instead of dead-lettering) when retries run out and no DLQ is set."""


@dataclass
class AgentOptions:
    """Settings for one agent process."""

    name: str  # "planner", "writer" or "reviewer"
    in_topic: str
    out_topic: Optional[str]
    group_id: str
    instance: str = ""
    commit_mode: str = "after"
    idempotent: bool = True
    max_attempts: int = config.MAX_ATTEMPTS
    dead_letter: bool = True
    key_mode: str = "correlation"
    offset_reset: str = "earliest"
    backoff: float = config.RETRY_BACKOFF_SECONDS
    bootstrap: Optional[str] = None
    store_path: Optional[str] = None


class AgentRunner:
    """Consume -> handle -> publish -> mark done -> commit, one message at a time."""

    def __init__(self, options: AgentOptions, handler: Handler) -> None:
        """Remember settings; nothing connects until run()."""
        if options.commit_mode not in ("after", "on_receive"):
            raise ValueError("commit_mode must be 'after' or 'on_receive'")
        if options.key_mode not in ("correlation", "entity", "none"):
            raise ValueError("key_mode must be 'correlation', 'entity' or 'none'")
        self.options = options
        self.handler = handler
        label = options.name.upper()
        self.label = f"{label}-{options.instance}" if options.instance else label
        self.log = get_logger(self.label)
        self.store = IdempotencyStore(options.store_path)
        self.consumer: Any = None
        self.producer: Any = None
        self.assigned: list = []
        self.processed = 0

    # ------------------------------------------------------------------ run
    async def run(self) -> None:
        """Connect, announce readiness and process messages until cancelled."""
        opts = self.options
        self.consumer = kafka_io.make_consumer(
            opts.in_topic,
            bootstrap=opts.bootstrap,
            group_id=opts.group_id,
            enable_auto_commit=False,
            auto_offset_reset=opts.offset_reset,
            session_timeout_ms=6000,  # a killed agent is noticed after 6 seconds
            heartbeat_interval_ms=2000,
        )
        self.producer = kafka_io.make_producer(opts.bootstrap)
        await start_with_retry(self.producer, "producer")
        await start_with_retry(self.consumer, "consumer")
        try:
            await self._announce(first=True)
            while True:
                batch = await self.consumer.getmany(timeout_ms=1000, max_records=1)
                await self._announce(first=False)
                for records in batch.values():
                    for record in records:
                        await self.process_record(record)
        finally:
            await self.consumer.stop()
            await self.producer.stop()
            self.store.close()

    async def _announce(self, first: bool) -> None:
        """Log the assigned partitions (at start, and whenever they change)."""
        current = sorted(tp.partition for tp in self.consumer.assignment())
        if first or current != self.assigned:
            for tp in self.consumer.assignment():
                await self.consumer.position(tp)  # resolve the start position now
            self.assigned = current
            opts = self.options
            attempts = "unbounded" if opts.max_attempts == 0 else opts.max_attempts
            text = (
                f"group={opts.group_id} topic={opts.in_topic} partitions={current} "
                f"commit_mode={opts.commit_mode} idempotent={opts.idempotent} "
                f"max_attempts={attempts} dead_letter={opts.dead_letter} "
                f"key_mode={opts.key_mode}"
            )
            if first:
                self.log.info("Consumer is ready and listening... %s", text)
            else:
                self.log.info("ASSIGNMENT CHANGED %s", text)

    # ------------------------------------------------------------- one message
    async def _commit(self, record: Any, note: str = "") -> None:
        """Commit offset+1 for the record's partition (a failure is only logged)."""
        try:
            await self.consumer.commit(
                {TopicPartition(record.topic, record.partition): record.offset + 1}
            )
            self.log.info(
                "COMMITTED offset=%d partition=%d%s",
                record.offset + 1,
                record.partition,
                f" {note}" if note else "",
            )
        except Exception as exc:  # the message will simply be delivered again
            self.log.info("COMMIT FAILED (message will be redelivered): %s", exc)

    def _key_for(
        self, out: Dict[str, Any], correlation_id: Optional[str]
    ) -> Optional[bytes]:
        """Choose the Kafka key of the published message."""
        mode = self.options.key_mode
        if mode == "none":
            return None
        if mode == "entity" and out.get("entity"):
            return str(out["entity"]).encode("utf-8")
        return correlation_id.encode("utf-8") if correlation_id else None

    async def process_record(self, record: Any) -> None:
        """Handle one Kafka record according to the options."""
        opts = self.options
        where = (
            f"topic={record.topic} partition={record.partition} offset={record.offset}"
        )
        try:
            payload: Optional[Dict[str, Any]] = kafka_io.loads(record.value)
        except ValueError:
            payload = None
        cid = payload.get("correlation_id") if payload else None
        cid = cid if isinstance(cid, str) and cid else None
        self.log.info("RECEIVED %s correlation_id=%s", where, cid)

        if opts.commit_mode == "on_receive":
            await self._commit(record, "(before processing)")

        if opts.idempotent and cid and self.store.is_done(opts.name, cid):
            count = self.store.note_duplicate(opts.name, cid)
            self.log.info(
                "DUPLICATE correlation_id=%s already processed -> skipped, no new "
                "output (duplicates skipped so far: %d)",
                cid,
                count,
            )
            if opts.commit_mode == "after":
                await self._commit(record)
            return

        ctx = {
            "agent": self.label,
            "instance": opts.instance,
            "partition": record.partition,
            "offset": record.offset,
        }
        out = await self._attempts(record, payload, cid, ctx)
        if out is _DEAD_LETTERED:
            if opts.commit_mode == "after":
                await self._commit(record, "(after dead-lettering)")
            return

        if out is not None and opts.out_topic:
            if cid:
                out["correlation_id"] = cid
            metadata = await self.producer.send_and_wait(
                opts.out_topic,
                kafka_io.dumps(out),
                key=self._key_for(out, cid),
            )
            self.log.info(
                "SENT topic=%s partition=%d offset=%d correlation_id=%s",
                metadata.topic,
                metadata.partition,
                metadata.offset,
                cid,
            )
        elif out is None:
            self.log.info("NO OUTPUT for correlation_id=%s (message skipped)", cid)
        if opts.idempotent and cid:
            self.store.mark_done(opts.name, cid)
        self.processed += 1
        if opts.commit_mode == "after":
            await self._commit(record)

    async def _attempts(
        self,
        record: Any,
        payload: Optional[Dict[str, Any]],
        cid: Optional[str],
        ctx: Dict[str, Any],
    ) -> Any:
        """Run the handler with retries; return its output or _DEAD_LETTERED."""
        opts = self.options
        limit = opts.max_attempts
        attempt = 0
        while True:
            attempt += 1
            shown = "unbounded" if limit == 0 else limit
            try:
                if payload is None:
                    raise ValueError("message value is not a valid JSON object")
                self.log.info(
                    "PROCESSING correlation_id=%s attempt=%d/%s", cid, attempt, shown
                )
                return await self.handler(payload, ctx)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.info(
                    "FAILED correlation_id=%s attempt=%d/%s error=%s: %s",
                    cid,
                    attempt,
                    shown,
                    type(exc).__name__,
                    exc,
                )
                if limit and attempt >= limit:
                    if not opts.dead_letter:
                        raise RetriesExhausted(
                            f"{attempt} attempts failed for correlation_id={cid}"
                        ) from exc
                    await self._dead_letter(record, cid, attempt, exc)
                    return _DEAD_LETTERED
                delay = min(opts.backoff * (2 ** (attempt - 1)), 5.0 if limit else 1.0)
                self.log.info("RETRY in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _dead_letter(
        self, record: Any, cid: Optional[str], attempts: int, error: Exception
    ) -> None:
        """Publish the failed message and the reason to <PREFIX>_dead_letter."""
        message = {
            "correlation_id": cid,
            "failed_stage": self.options.name,
            "error": f"{type(error).__name__}: {error}",
            "attempts": attempts,
            "source_topic": record.topic,
            "source_partition": record.partition,
            "source_offset": record.offset,
            "original": (record.value or b"").decode("utf-8", "replace"),
            "failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        metadata = await self.producer.send_and_wait(
            config.DEAD_LETTER_TOPIC,
            kafka_io.dumps(message),
            key=cid.encode("utf-8") if cid else None,
        )
        self.log.info(
            "DEAD LETTER after %d attempts -> topic=%s partition=%d offset=%d "
            "correlation_id=%s",
            attempts,
            metadata.topic,
            metadata.partition,
            metadata.offset,
            cid,
        )
        self.log.info("DEAD LETTER MESSAGE %s", json.dumps(message))


_DEAD_LETTERED = object()
