"""Small Kafka helpers shared by every HW8 component.

All producers and consumers are created here, so the offline tests can swap in
the in-memory broker from hw8/fake_kafka.py by replacing two names.
"""

import json
import time
from typing import Any, Dict, List, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition

from hw8 import config


def dumps(message: Dict[str, Any]) -> bytes:
    """Encode a message dict as UTF-8 JSON bytes."""
    return json.dumps(message).encode("utf-8")


def loads(raw: Optional[bytes]) -> Dict[str, Any]:
    """Decode JSON bytes into a dict; raise ValueError if it is not an object."""
    if raw is None:
        raise ValueError("empty message value")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"message is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("message JSON must be an object")
    return value


def make_producer(bootstrap: Optional[str] = None, **kwargs: Any) -> Any:
    """Create (not start) a Kafka producer."""
    return AIOKafkaProducer(
        bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS, **kwargs
    )


def make_consumer(*topics: str, bootstrap: Optional[str] = None, **kwargs: Any) -> Any:
    """Create (not start) a Kafka consumer."""
    return AIOKafkaConsumer(
        *topics, bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS, **kwargs
    )


async def end_offsets(topic: str, bootstrap: Optional[str] = None) -> Dict[int, int]:
    """Return {partition: next offset to be written} for a topic."""
    consumer = make_consumer(bootstrap=bootstrap, enable_auto_commit=False)
    await consumer.start()
    try:
        partitions = [
            TopicPartition(topic, p) for p in range(config.TOPIC_PARTITIONS[topic])
        ]
        consumer.assign(partitions)
        ends = await consumer.end_offsets(partitions)
        return {tp.partition: int(offset) for tp, offset in ends.items()}
    finally:
        await consumer.stop()


async def read_since(
    topic: str,
    offsets: Dict[int, int],
    idle_seconds: float = 2.0,
    bootstrap: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read every message written to a topic at or after the given offsets.

    Stops once nothing new arrives for idle_seconds. Each row has partition,
    offset, key (str or None) and value (decoded dict, or raw text if the value
    is not JSON).
    """
    consumer = make_consumer(bootstrap=bootstrap, enable_auto_commit=False)
    await consumer.start()
    rows: List[Dict[str, Any]] = []
    try:
        partitions = [TopicPartition(topic, p) for p in sorted(offsets)]
        consumer.assign(partitions)
        for tp in partitions:
            consumer.seek(tp, offsets[tp.partition])
        last_new = time.monotonic()
        while time.monotonic() - last_new < idle_seconds:
            batch = await consumer.getmany(timeout_ms=500)
            for records in batch.values():
                for record in records:
                    try:
                        value: Any = loads(record.value)
                    except ValueError:
                        value = (record.value or b"").decode("utf-8", "replace")
                    key = record.key.decode("utf-8") if record.key else None
                    rows.append(
                        {
                            "partition": record.partition,
                            "offset": record.offset,
                            "key": key,
                            "value": value,
                        }
                    )
                    last_new = time.monotonic()
    finally:
        await consumer.stop()
    return rows


async def committed_offsets(
    group: str, topic: str, bootstrap: Optional[str] = None
) -> Dict[int, Optional[int]]:
    """Return {partition: committed offset or None} for a consumer group."""
    consumer = make_consumer(
        bootstrap=bootstrap, group_id=group, enable_auto_commit=False
    )
    await consumer.start()
    try:
        result: Dict[int, Optional[int]] = {}
        for partition in range(config.TOPIC_PARTITIONS[topic]):
            tp = TopicPartition(topic, partition)
            consumer.assign([tp])
            result[partition] = await consumer.committed(tp)
        return result
    finally:
        await consumer.stop()


async def ensure_topics(bootstrap: Optional[str] = None) -> Dict[str, int]:
    """Create any missing HW8 topic and return {topic: partitions} as found.

    docker compose already creates the topics; this is a safety net so the
    scripts also work when only the broker is running.
    """
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import TopicAlreadyExistsError

    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [
            NewTopic(name=name, num_partitions=count, replication_factor=1)
            for name, count in config.TOPIC_PARTITIONS.items()
            if name not in existing
        ]
        if missing:
            try:
                await admin.create_topics(missing)
            except TopicAlreadyExistsError:
                pass
        described = await admin.describe_topics(list(config.TOPIC_PARTITIONS))
        return {item["topic"]: len(item["partitions"]) for item in described}
    finally:
        await admin.close()
