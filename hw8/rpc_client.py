"""Kafka request/response client used by homework_demo.py and the FastAPI wrapper.

The client creates the correlation_id once, sends the request to
<PREFIX>_entity_requests and waits for the response with the same
correlation_id on <PREFIX>_entity_responses.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from aiokafka import TopicPartition

from hw8 import config, kafka_io
from hw8.logs import get_logger


class RpcTimeout(Exception):
    """Raised when no response with the right correlation_id arrives in time."""

    def __init__(self, correlation_id: str) -> None:
        """Remember which request timed out."""
        super().__init__(f"Timeout waiting for correlation_id {correlation_id}")
        self.correlation_id = correlation_id


async def start_with_retry(client: Any, what: str, seconds: float = 60.0) -> None:
    """Start a Kafka client, retrying while the broker is still coming up."""
    log = get_logger("KAFKA")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            await client.start()
            return
        except Exception as exc:  # broker not ready yet
            if loop.time() > deadline:
                raise
            log.info("%s could not connect (attempt %d): %s", what, attempt, exc)
            await asyncio.sleep(2)


class KafkaRPC:
    """Send a request over Kafka and wait for the matching response."""

    def __init__(
        self,
        bootstrap: Optional[str] = None,
        request_topic: str = config.REQUEST_TOPIC,
        response_topic: str = config.RESPONSE_TOPIC,
        timeout: float = config.RPC_TIMEOUT_SECONDS,
        component: str = "CLIENT",
        verbose: bool = True,
    ) -> None:
        """Store settings; nothing connects until start()."""
        self.bootstrap = bootstrap
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.timeout = timeout
        self.verbose = verbose
        self.log = get_logger(component)
        self.producer: Any = None
        self.consumer: Any = None
        self.pending: Dict[str, asyncio.Future] = {}
        self.listener: Optional[asyncio.Task] = None
        # structured record of what this client sent and received (for the demo)
        self.events: List[Dict[str, Any]] = []

    async def start(self) -> None:
        """Connect and start listening on the response topic.

        The consumer is assigned directly (no group) and moved to the end of
        the topic, so it only sees responses created after it started.
        """
        self.producer = kafka_io.make_producer(self.bootstrap)
        await start_with_retry(self.producer, "producer")
        self.consumer = kafka_io.make_consumer(
            bootstrap=self.bootstrap, enable_auto_commit=False
        )
        await start_with_retry(self.consumer, "consumer")
        partitions = [
            TopicPartition(self.response_topic, p)
            for p in range(config.TOPIC_PARTITIONS[self.response_topic])
        ]
        self.consumer.assign(partitions)
        await self.consumer.seek_to_end(*partitions)
        for tp in partitions:
            await self.consumer.position(tp)  # forces the position to resolve
        self.listener = asyncio.create_task(self._listen())
        self.log.info("Listening for responses on topic: %s", self.response_topic)

    async def stop(self) -> None:
        """Stop the listener and close both Kafka clients."""
        if self.listener:
            self.listener.cancel()
            try:
                await self.listener
            except asyncio.CancelledError:
                pass
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def _listen(self) -> None:
        """Read the response topic and complete the matching pending future."""
        while True:
            batch = await self.consumer.getmany(timeout_ms=500)
            for records in batch.values():
                for record in records:
                    self._on_record(record)

    def _on_record(self, record: Any) -> None:
        """Handle one response record."""
        try:
            response = kafka_io.loads(record.value)
        except ValueError:
            return
        correlation_id = response.get("correlation_id")
        future = self.pending.pop(correlation_id, None)
        if future is None:
            if self.verbose:
                self.log.info(
                    "ignored response for unknown correlation_id=%s", correlation_id
                )
            return
        self.events.append(
            {
                "ts": time.time(),
                "component": "CLIENT",
                "event": "response_received",
                "correlation_id": correlation_id,
                "topic": record.topic,
                "partition": record.partition,
                "offset": record.offset,
                "success": response.get("success"),
            }
        )
        if self.verbose:
            self.log.info(
                "RESPONSE RECEIVED topic=%s partition=%d offset=%d correlation_id=%s",
                record.topic,
                record.partition,
                record.offset,
                correlation_id,
            )
            self.log.info("RESPONSE %s", json.dumps(response))
        if not future.done():
            future.set_result(response)

    async def request(
        self,
        operation: str,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send one request and return the full response message.

        The correlation_id is created here once (unless the caller supplies
        one) and is never changed afterwards.
        """
        correlation_id = correlation_id or str(uuid.uuid4())
        message = {
            "correlation_id": correlation_id,
            "reply_to": self.response_topic,
            "operation": operation,
            "data": data,
        }
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[correlation_id] = future
        metadata = await self.producer.send_and_wait(
            self.request_topic, kafka_io.dumps(message)
        )
        self.events.append(
            {
                "ts": time.time(),
                "component": "CLIENT",
                "event": "request_sent",
                "correlation_id": correlation_id,
                "operation": operation,
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
            }
        )
        if self.verbose:
            self.log.info(
                "REQUEST SENT topic=%s partition=%d offset=%d correlation_id=%s",
                metadata.topic,
                metadata.partition,
                metadata.offset,
                correlation_id,
            )
            self.log.info("REQUEST %s", json.dumps(message))
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.pending.pop(correlation_id, None)
            raise RpcTimeout(correlation_id) from None
