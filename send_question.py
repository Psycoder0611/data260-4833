"""Send one question into s4833_inbox and (optionally) follow it to s4833_final.

Run:  python send_question.py --wait --journey
      python send_question.py --question "Who can edit a trial listing?" --wait
"""

import argparse
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List

from hw8 import config, kafka_io
from hw8.logs import get_logger, run_logged
from hw8.pipeline import now_iso

DEFAULT_QUESTION = (
    "What should a sponsor check before publishing a Phase II cardiology "
    "clinical trial listing?"
)
STAGES = [
    config.INBOX_TOPIC,
    config.TASKS_TOPIC,
    config.DRAFTS_TOPIC,
    config.FINAL_TOPIC,
]


async def send(question: str, wait: bool, journey: bool, timeout: float) -> int:
    """Send the question; return 0 if the final message arrived (or no wait)."""
    log = get_logger("YOU")
    starts: Dict[str, Dict[int, int]] = {}
    for topic in STAGES:
        starts[topic] = await kafka_io.end_offsets(topic)
    correlation_id = str(uuid.uuid4())
    message = {
        "correlation_id": correlation_id,
        "stage": "question",
        "question": question,
        "created_at": now_iso(),
    }
    producer = kafka_io.make_producer()
    await producer.start()
    try:
        metadata = await producer.send_and_wait(
            config.INBOX_TOPIC,
            kafka_io.dumps(message),
            key=correlation_id.encode("utf-8"),
        )
    finally:
        await producer.stop()
    log.info(
        "SENT topic=%s partition=%d offset=%d correlation_id=%s",
        metadata.topic,
        metadata.partition,
        metadata.offset,
        correlation_id,
    )
    log.info("MESSAGE %s", json.dumps(message))
    if not wait:
        return 0

    final: Dict[str, Any] = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not final:
        rows = await kafka_io.read_since(
            config.FINAL_TOPIC, starts[config.FINAL_TOPIC], 1.0
        )
        for row in rows:
            value = row["value"]
            if (
                isinstance(value, dict)
                and value.get("correlation_id") == correlation_id
            ):
                final = value
    if not final:
        log.info(
            "TIMEOUT no final message for correlation_id=%s after %ds",
            correlation_id,
            timeout,
        )
        return 1
    log.info(
        "FINAL RECEIVED from topic=%s correlation_id=%s",
        config.FINAL_TOPIC,
        correlation_id,
    )
    print(json.dumps(final, indent=2))
    if journey:
        await show_journey(correlation_id, starts)
    return 0


async def show_journey(correlation_id: str, starts: Dict[str, Dict[int, int]]) -> None:
    """Print the message with this correlation_id from every topic, in stage order."""
    log = get_logger("JOURNEY")
    log.info("message journey for correlation_id=%s", correlation_id)
    for topic in STAGES:
        rows: List[Dict[str, Any]] = await kafka_io.read_since(
            topic, starts[topic], 1.0
        )
        for row in rows:
            value = row["value"]
            if (
                isinstance(value, dict)
                and value.get("correlation_id") == correlation_id
            ):
                keys = ",".join(k for k in value if k != "correlation_id")
                log.info(
                    "%s partition=%d offset=%d key=%s fields=[%s]",
                    topic,
                    row["partition"],
                    row["offset"],
                    row["key"],
                    keys,
                )


def main() -> None:
    """Parse arguments and send the question."""
    parser = argparse.ArgumentParser(description="Send a question to the pipeline")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--wait", action="store_true", help="wait for s4833_final")
    parser.add_argument(
        "--journey", action="store_true", help="list each topic's message"
    )
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    with run_logged("Part 2 send_question"):
        raise SystemExit(
            asyncio.run(send(args.question, args.wait, args.journey, args.timeout))
        )


if __name__ == "__main__":
    main()
