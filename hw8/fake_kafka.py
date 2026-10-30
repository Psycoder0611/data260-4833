"""A small in-memory Kafka used only by the offline tests.

It copies the parts of the aiokafka API that HW8 uses: producer send_and_wait,
consumer groups with partitions shared between members, manual commits,
committed offsets that survive a consumer restart, reset policies, assign/seek,
and the same murmur2 key-to-partition rule as the real client. It is NOT used
for any reported result; all reported runs use the real Kafka in Docker.

Simplifications: auto-commit commits right after records are returned, and a
rebalance is applied instantly when a member joins or leaves.
"""

import asyncio
import random
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from aiokafka import TopicPartition
from aiokafka.partitioner import murmur2

from hw8 import config


class FakeBroker:
    """Holds topic logs, committed offsets and consumer-group membership."""

    def __init__(self, seed: int = 0) -> None:
        """Create an empty broker; seed controls the unkeyed partition choice."""
        self.logs: Dict[str, List[List[SimpleNamespace]]] = {}
        self.committed: Dict[Tuple[str, str, int], int] = {}
        self.groups: Dict[str, List["FakeConsumer"]] = {}
        self.waiters: List[asyncio.Future] = []
        self.random = random.Random(seed)

    def partitions(self, topic: str) -> int:
        """Number of partitions (topics are created on first use)."""
        if topic not in self.logs:
            count = config.TOPIC_PARTITIONS.get(topic, 1)
            self.logs[topic] = [[] for _ in range(count)]
        return len(self.logs[topic])

    def append(
        self,
        topic: str,
        value: Optional[bytes],
        key: Optional[bytes],
        partition: Optional[int],
    ) -> SimpleNamespace:
        """Write one record and return its metadata."""
        count = self.partitions(topic)
        if partition is None:
            if key is None:
                partition = self.random.randrange(count)
            else:
                partition = (murmur2(key) & 0x7FFFFFFF) % count
        log = self.logs[topic][partition]
        record = SimpleNamespace(
            topic=topic,
            partition=partition,
            offset=len(log),
            key=key,
            value=value,
            timestamp=int(time.time() * 1000),
            headers=[],
        )
        log.append(record)
        self.wake()
        return record

    def wake(self) -> None:
        """Wake every consumer waiting for data."""
        for waiter in self.waiters:
            if not waiter.done():
                waiter.set_result(None)
        self.waiters.clear()

    def rebalance(self, group: str) -> None:
        """Share the partitions of the group's topics between its members."""
        members = self.groups.get(group, [])
        topics = sorted({t for member in members for t in member.topics})
        all_partitions = [
            TopicPartition(t, p) for t in topics for p in range(self.partitions(t))
        ]
        for member in members:
            member.set_assignment(set())
        for index, tp in enumerate(all_partitions):
            if members:
                members[index % len(members)].assignment_set.add(tp)
        for member in members:
            member.reset_positions()
        self.wake()


class FakeProducer:
    """Stand-in for AIOKafkaProducer."""

    broker: FakeBroker

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept (and ignore) the real constructor arguments."""
        self.started = False

    async def start(self) -> None:
        """Mark the producer as started."""
        self.started = True

    async def stop(self) -> None:
        """Mark the producer as stopped."""
        self.started = False

    async def send_and_wait(
        self,
        topic: str,
        value: Optional[bytes] = None,
        key: Optional[bytes] = None,
        partition: Optional[int] = None,
        **_: Any,
    ) -> SimpleNamespace:
        """Append a record to the topic."""
        if not self.started:
            raise RuntimeError("producer is not started")
        return self.broker.append(topic, value, key, partition)


class FakeConsumer:
    """Stand-in for AIOKafkaConsumer (group mode and assign mode)."""

    broker: FakeBroker

    def __init__(
        self,
        *topics: str,
        group_id: Optional[str] = None,
        enable_auto_commit: bool = True,
        auto_offset_reset: str = "latest",
        **_: Any,
    ) -> None:
        """Remember topics, group and policies."""
        self.topics = list(topics)
        self.group_id = group_id
        self.auto_commit = enable_auto_commit
        self.reset = auto_offset_reset
        self.assignment_set: Set[TopicPartition] = set()
        self.positions: Dict[TopicPartition, int] = {}
        self.started = False

    # ---- lifecycle
    async def start(self) -> None:
        """Join the group (if any) and take part in a rebalance."""
        self.started = True
        if self.group_id and self.topics:
            self.broker.groups.setdefault(self.group_id, []).append(self)
            self.broker.rebalance(self.group_id)

    async def stop(self) -> None:
        """Leave the group; the other members get the partitions."""
        if not self.started:
            return
        self.started = False
        if self.group_id and self in self.broker.groups.get(self.group_id, []):
            self.broker.groups[self.group_id].remove(self)
            self.broker.rebalance(self.group_id)

    # ---- assignment and positions
    def assignment(self) -> Set[TopicPartition]:
        """Return the partitions currently assigned to this consumer."""
        return set(self.assignment_set)

    def set_assignment(self, partitions: Set[TopicPartition]) -> None:
        """Replace the assignment."""
        self.assignment_set = set(partitions)

    def assign(self, partitions: List[TopicPartition]) -> None:
        """Manual assignment (no group)."""
        self.assignment_set = set(partitions)
        self.reset_positions()

    def reset_positions(self) -> None:
        """Start every assigned partition at committed offset or reset policy."""
        self.positions = {}
        for tp in self.assignment_set:
            committed = self.broker.committed.get(
                (self.group_id or "", tp.topic, tp.partition)
            )
            if committed is not None:
                self.positions[tp] = committed
            elif self.reset == "earliest":
                self.positions[tp] = 0
            else:
                self.positions[tp] = self._end(tp)

    def _end(self, tp: TopicPartition) -> int:
        """Next offset to be written on a partition."""
        self.broker.partitions(tp.topic)
        return len(self.broker.logs[tp.topic][tp.partition])

    async def position(self, tp: TopicPartition) -> int:
        """Current fetch position."""
        return self.positions[tp]

    def seek(self, tp: TopicPartition, offset: int) -> None:
        """Move the fetch position."""
        self.positions[tp] = offset

    async def seek_to_end(self, *partitions: TopicPartition) -> None:
        """Move positions to the end of the log."""
        for tp in partitions or tuple(self.assignment_set):
            self.positions[tp] = self._end(tp)

    async def end_offsets(self, partitions: List[TopicPartition]) -> Dict[Any, int]:
        """Return the end offset of each partition."""
        return {tp: self._end(tp) for tp in partitions}

    # ---- commits
    async def commit(self, offsets: Optional[Dict[TopicPartition, int]] = None) -> None:
        """Store committed offsets for the group."""
        if not self.group_id:
            raise RuntimeError("commit needs a group_id")
        for tp, offset in (offsets or dict(self.positions)).items():
            self.broker.committed[(self.group_id, tp.topic, tp.partition)] = offset

    async def committed(self, tp: TopicPartition) -> Optional[int]:
        """Committed offset for this group, or None."""
        return self.broker.committed.get((self.group_id or "", tp.topic, tp.partition))

    # ---- fetching
    def _take(self, limit: int) -> List[SimpleNamespace]:
        """Take up to limit available records, lowest partition first."""
        out: List[SimpleNamespace] = []
        for tp in sorted(self.assignment_set):
            self.broker.partitions(tp.topic)
            log = self.broker.logs[tp.topic]
            while self.positions[tp] < len(log[tp.partition]) and len(out) < limit:
                out.append(log[tp.partition][self.positions[tp]])
                self.positions[tp] += 1
        if out and self.auto_commit and self.group_id:
            for record in out:
                key = (self.group_id, record.topic, record.partition)
                self.broker.committed[key] = record.offset + 1
        return out

    async def getmany(
        self, *partitions: Any, timeout_ms: int = 0, max_records: Optional[int] = None
    ) -> Dict[TopicPartition, List[SimpleNamespace]]:
        """Return available records, waiting up to timeout_ms for the first."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            taken = self._take(max_records or 1000)
            if taken:
                result: Dict[TopicPartition, List[SimpleNamespace]] = {}
                for record in taken:
                    tp = TopicPartition(record.topic, record.partition)
                    result.setdefault(tp, []).append(record)
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {}
            waiter = asyncio.get_running_loop().create_future()
            self.broker.waiters.append(waiter)
            try:
                await asyncio.wait_for(waiter, timeout=remaining)
            except asyncio.TimeoutError:
                return {}

    async def getone(self) -> SimpleNamespace:
        """Wait for exactly one record."""
        while True:
            batch = await self.getmany(timeout_ms=1000, max_records=1)
            for records in batch.values():
                return records[0]

    def __aiter__(self) -> "FakeConsumer":
        """Allow ``async for record in consumer``."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Next record."""
        return await self.getone()


def install(monkeypatch: Any, broker: FakeBroker) -> None:
    """Point hw8.kafka_io at the fake broker for the duration of a test."""
    from hw8 import kafka_io

    producer_class = type("BoundProducer", (FakeProducer,), {"broker": broker})
    consumer_class = type("BoundConsumer", (FakeConsumer,), {"broker": broker})
    monkeypatch.setattr(kafka_io, "AIOKafkaProducer", producer_class)
    monkeypatch.setattr(kafka_io, "AIOKafkaConsumer", consumer_class)
