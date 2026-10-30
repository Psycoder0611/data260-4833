"""Part 1 worker: consumes <PREFIX>_entity_requests and replies on the reply_to topic.

Run:  python -m hw8.entity_worker      (the Docker "worker" service does this)

For every request the worker logs: received, processing, reply sent. It sends
the response first and commits the offset only after the reply is out, so a
crash before that point means the request is delivered again. A repeated
correlation_id gets the saved response back instead of a second entity.
"""

import asyncio
import json
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aiokafka import TopicPartition

from hw8 import config, kafka_io
from hw8.entity_service import process_request
from hw8.logs import append_jsonl, get_logger
from hw8.rpc_client import start_with_retry

CACHE_LIMIT = 10_000


class EntityWorker:
    """Reads requests, runs CREATE/GET on a plain dictionary and replies."""

    def __init__(
        self,
        bootstrap: Optional[str] = None,
        trace_path: Optional[Path] = None,
        group_id: str = config.WORKER_GROUP,
    ) -> None:
        """Set up empty state; nothing connects until run()."""
        self.bootstrap = bootstrap
        self.group_id = group_id
        self.trace_path = trace_path
        self.store: Dict[str, Dict[str, Any]] = {}
        self.responses: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.log = get_logger("WORKER")
        self.consumer: Any = None
        self.producer: Any = None

    def trace(self, event: str, **fields: Any) -> None:
        """Append one event to the worker trace file (if tracing is on)."""
        if self.trace_path is None:
            return
        append_jsonl(
            self.trace_path,
            {
                "ts": time.time(),
                "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "event": event,
                **fields,
            },
        )

    async def run(self) -> None:
        """Start the clients and handle requests until cancelled."""
        self.consumer = kafka_io.make_consumer(
            config.REQUEST_TOPIC,
            bootstrap=self.bootstrap,
            group_id=self.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        self.producer = kafka_io.make_producer(self.bootstrap)
        await start_with_retry(self.producer, "producer")
        await start_with_retry(self.consumer, "consumer")
        try:
            self.log.info("Consumer is ready and listening...")
            self.log.info(
                "request topic=%s response topic=%s group=%s",
                config.REQUEST_TOPIC,
                config.RESPONSE_TOPIC,
                self.group_id,
            )
            while True:
                batch = await self.consumer.getmany(timeout_ms=1000, max_records=1)
                for records in batch.values():
                    for record in records:
                        await self.handle(record)
        finally:
            await self.consumer.stop()
            await self.producer.stop()

    async def handle(self, record: Any) -> None:
        """Process one request record and commit its offset after the reply."""
        where = (
            f"topic={record.topic} partition={record.partition} offset={record.offset}"
        )
        raw_text = (record.value or b"").decode("utf-8", "replace")
        correlation_id: Optional[str] = None
        reply_to = config.RESPONSE_TOPIC
        operation: Any = None
        try:
            request = kafka_io.loads(record.value)
        except ValueError as exc:
            self.log.info("REQUEST RECEIVED %s (unreadable)", where)
            self.trace("received", where=where, raw=raw_text[:200])
            result: Dict[str, Any] = {"success": False, "error": f"Bad message: {exc}"}
        else:
            raw_cid = request.get("correlation_id")
            correlation_id = raw_cid if isinstance(raw_cid, str) and raw_cid else None
            operation = request.get("operation")
            candidate = request.get("reply_to")
            if isinstance(candidate, str) and candidate.startswith(f"{config.PREFIX}_"):
                reply_to = candidate
            self.log.info(
                "REQUEST RECEIVED %s correlation_id=%s", where, correlation_id
            )
            self.log.info("REQUEST %s", json.dumps(request))
            self.trace(
                "received",
                correlation_id=correlation_id,
                operation=operation,
                partition=record.partition,
                offset=record.offset,
            )
            envelope_error = None
            if correlation_id is None:
                envelope_error = "correlation_id is required"
            elif candidate is None:
                envelope_error = "reply_to is required"
            elif candidate != reply_to:
                envelope_error = "Invalid reply_to topic"
            elif "data" not in request:
                envelope_error = "data is required"
            if envelope_error is not None:
                result = {"success": False, "error": envelope_error}
            elif correlation_id in self.responses:
                self.log.info(
                    "DUPLICATE correlation_id=%s -> replaying saved response, "
                    "no new entity created",
                    correlation_id,
                )
                result = {
                    k: v
                    for k, v in self.responses[correlation_id].items()
                    if k not in ("correlation_id", "operation")
                }
            else:
                self.log.info(
                    "PROCESSING operation=%s correlation_id=%s",
                    operation,
                    correlation_id,
                )
                self.trace(
                    "processing", correlation_id=correlation_id, operation=operation
                )
                result = process_request(operation, request.get("data", {}), self.store)
        response = {"correlation_id": correlation_id, "operation": operation, **result}
        if correlation_id is not None:
            self.responses[correlation_id] = response
            while len(self.responses) > CACHE_LIMIT:
                self.responses.popitem(last=False)
        self.log.info(
            "PROCESSED success=%s correlation_id=%s",
            response.get("success"),
            correlation_id,
        )
        metadata = await self.producer.send_and_wait(reply_to, kafka_io.dumps(response))
        self.log.info(
            "RESPONSE SENT topic=%s partition=%d offset=%d correlation_id=%s",
            metadata.topic,
            metadata.partition,
            metadata.offset,
            correlation_id,
        )
        self.log.info("RESPONSE %s", json.dumps(response))
        self.trace(
            "reply_sent",
            correlation_id=correlation_id,
            topic=metadata.topic,
            partition=metadata.partition,
            offset=metadata.offset,
            success=response.get("success"),
        )
        await self.consumer.commit(
            {TopicPartition(record.topic, record.partition): record.offset + 1}
        )


def main() -> None:
    """Entry point for ``python -m hw8.entity_worker``."""
    trace_path = config.WORKER_TRACE_PATH if config.TRACE_ENABLED else None
    worker = EntityWorker(trace_path=trace_path)
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
