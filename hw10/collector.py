# ruff: noqa: E501
"""Read the pipeline topics and join plan, draft and final by correlation_id.

The Collector consumes s4833_tasks (plan), s4833_drafts (draft), s4833_final (final)
and s4833_dead_letter. Every Kafka record is kept exactly as received (topic,
partition, offset, timestamp, key, decoded value), so the evaluation can be
reproduced from the saved file without Kafka. join_by_correlation() is a pure
function and is what the offline tests exercise.
"""

import asyncio
import json
import time
from typing import Any, Dict, Iterable, List, Optional

from aiokafka import TopicPartition

from hw8 import config as hw8_config
from hw8 import kafka_io

from hw10 import config

ROLE_BY_TOPIC = {
    config.TASKS_TOPIC: "plan",
    config.DRAFTS_TOPIC: "draft",
    config.FINAL_TOPIC: "final",
    config.DEAD_LETTER_TOPIC: "dead_letter",
}


def record_to_row(record: Any) -> Dict[str, Any]:
    """Keep a Kafka record in a plain, JSON-friendly dict."""
    try:
        value: Any = kafka_io.loads(record.value)
    except ValueError:
        value = {"_malformed": (record.value or b"").decode("utf-8", "replace")}
    key = record.key.decode("utf-8") if record.key else None
    return {
        "topic": record.topic,
        "partition": record.partition,
        "offset": record.offset,
        "timestamp_ms": getattr(record, "timestamp", None),
        "key": key,
        "value": value,
    }


def join_by_correlation(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{correlation_id: {"plan", "draft", "final", "dead_letter", "issues"}}.

    If a stage appears twice (a redelivery) the later record wins. A message whose
    value is not a JSON object, or has no correlation_id, is reported in "issues"
    under the key "_unjoined" instead of being dropped silently.
    """
    joined: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        role = ROLE_BY_TOPIC.get(row["topic"])
        value = row.get("value")
        cid = value.get("correlation_id") if isinstance(value, dict) else None
        if role is None:
            continue
        if not isinstance(cid, str) or not cid:
            bucket = joined.setdefault("_unjoined", {"issues": []})
            bucket["issues"].append(
                f"{row['topic']} partition={row['partition']} offset={row['offset']}: no correlation_id or malformed value"
            )
            continue
        entry = joined.setdefault(cid, {"issues": []})
        entry[role] = row
    for cid, entry in joined.items():
        if cid == "_unjoined":
            continue
        entry["issues"] = problems(entry)
    return joined


def problems(entry: Dict[str, Any]) -> List[str]:
    """What is missing or malformed in one joined trace."""
    found: List[str] = []
    for role in ("plan", "draft", "final"):
        row = entry.get(role)
        if row is None:
            if role == "final" and entry.get("dead_letter"):
                continue
            found.append(f"missing {role} message")
            continue
        value = row["value"]
        if "_malformed" in value:
            found.append(f"{role} message is not valid JSON")
        elif role == "plan" and not (
            isinstance(value.get("plan"), list) and value["plan"]
        ):
            found.append("plan is empty or not a list")
        elif role == "draft" and not str(value.get("draft", "")).strip():
            found.append("draft is empty")
        elif role == "final" and not str(value.get("answer", "")).strip():
            found.append("final answer is empty")
    if entry.get("dead_letter"):
        found.append("message was dead-lettered")
    return found


def bundle_for(trace_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Self-contained record of one trace's messages (saved to reports/hw10/raw/joined/)."""
    return {
        "trace_id": trace_id,
        "plan": entry.get("plan"),
        "draft": entry.get("draft"),
        "final": entry.get("final"),
        "dead_letter": entry.get("dead_letter"),
        "issues": entry.get("issues", []),
    }


def save_bundle(bundle: Dict[str, Any]) -> str:
    """Write the bundle next to the other raw files; returns the path."""
    config.JOINED_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOINED_DIR / f"{bundle['trace_id']}.json"
    path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    return str(path)


class Collector:
    """Consumer over the four pipeline topics that keeps every record it sees."""

    def __init__(self, bootstrap: Optional[str] = None) -> None:
        """Nothing connects until start()."""
        self.bootstrap = bootstrap
        self.consumer: Any = None
        self.rows: List[Dict[str, Any]] = []

    async def start(self, from_beginning: bool = False) -> None:
        """Connect and position at the end (live use) or the beginning (replay)."""
        from hw8.rpc_client import start_with_retry

        self.consumer = kafka_io.make_consumer(
            bootstrap=self.bootstrap, enable_auto_commit=False
        )
        await start_with_retry(self.consumer, "collector")
        partitions = [
            TopicPartition(topic, p)
            for topic in ROLE_BY_TOPIC
            for p in range(hw8_config.TOPIC_PARTITIONS[topic])
        ]
        self.consumer.assign(partitions)
        if from_beginning:
            for tp in partitions:
                self.consumer.seek(tp, 0)
        else:
            await self.consumer.seek_to_end(*partitions)
            for tp in partitions:
                await self.consumer.position(tp)  # resolve now, before anything is sent

    async def stop(self) -> None:
        """Disconnect."""
        if self.consumer is not None:
            await self.consumer.stop()
            self.consumer = None

    async def poll(self, timeout_ms: int = 300) -> int:
        """Fetch what is available; returns the number of new records."""
        batch = await self.consumer.getmany(timeout_ms=timeout_ms)
        count = 0
        for records in batch.values():
            for record in records:
                self.rows.append(record_to_row(record))
                count += 1
        return count

    def entry(self, trace_id: str) -> Dict[str, Any]:
        """The joined entry for one trace (empty entry if nothing was seen)."""
        joined = join_by_correlation(
            r for r in self.rows if _cid(r) == trace_id
        )
        return joined.get(trace_id, {"issues": ["no messages seen"]})

    async def wait_for(
        self, trace_id: str, timeout: float, settle: float = 2.0
    ) -> Dict[str, Any]:
        """Wait until the trace has a final answer or a dead letter, or time runs out.

        Returns the joined entry. entry["timed_out"] is True if nothing finished.
        After the end message appears it keeps reading for up to `settle` seconds
        so the plan and the draft (separate partitions) are also in.
        """
        deadline = time.monotonic() + timeout
        ended_at: Optional[float] = None
        while True:
            await self.poll(200)
            entry = self.entry(trace_id)
            done = "final" in entry or "dead_letter" in entry
            if done and ended_at is None:
                ended_at = time.monotonic()
            if done:
                complete = "plan" in entry and (
                    "draft" in entry or "dead_letter" in entry
                )
                if complete or time.monotonic() - ended_at >= settle:
                    entry["timed_out"] = False
                    return entry
            if time.monotonic() > deadline:
                entry["timed_out"] = True
                return entry
            await asyncio.sleep(0)


def _cid(row: Dict[str, Any]) -> Optional[str]:
    """correlation_id of a row, if it has one."""
    value = row.get("value")
    return value.get("correlation_id") if isinstance(value, dict) else None
