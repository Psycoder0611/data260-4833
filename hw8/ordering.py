"""Part 3 ordering test: generate 20 related messages and check processing order.

The messages are generated from VERIFY_SEED, so the same 20 messages (entities,
sequence numbers and work times) are produced on every run. "Related" means
several messages about the same clinical trial (the entity); within one entity
the sequence numbers 1, 2, 3, ... must be processed in order.
"""

import random
from typing import Any, Dict, List

from aiokafka.partitioner import murmur2

from hw8 import config

# Five trial codes. With 2 partitions murmur2 puts 106 and 110 on partition 0 and
# 107, 108 and 109 on partition 1, so a keyed run uses both Writers.
ENTITIES = [f"CT-2026-{n}" for n in range(106, 111)]
MESSAGE_COUNT = 20


def key_partition(key: str, partitions: int = 2) -> int:
    """Partition the real producer picks for this key (same murmur2 rule)."""
    return (murmur2(key.encode("utf-8")) & 0x7FFFFFFF) % partitions


def generate_messages(
    run_tag: str,
    seed: int = config.VERIFY_SEED,
    count: int = MESSAGE_COUNT,
    work_scale: float = 1.0,
) -> List[Dict[str, Any]]:
    """Return count related task messages, in the order they will be sent."""
    rng = random.Random(seed)
    per_entity = count // len(ENTITIES)
    order = [entity for entity in ENTITIES for _ in range(per_entity)]
    rng.shuffle(order)
    next_seq: Dict[str, int] = {}
    messages: List[Dict[str, Any]] = []
    for index, entity in enumerate(order):
        next_seq[entity] = next_seq.get(entity, 0) + 1
        seq = next_seq[entity]
        messages.append(
            {
                "correlation_id": f"ord-{run_tag}-{index:02d}",
                "stage": "plan",
                "question": f"Apply update {seq} to trial listing {entity}",
                "plan": [
                    "Read the current listing",
                    f"Apply update {seq}",
                    "Confirm the listing",
                ],
                "entity": entity,
                "seq": seq,
                "index": index,
                "work_ms": round(rng.randint(80, 400) * work_scale),
                "test_run": run_tag,
            }
        )
    return messages


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check processing order from the Writers' records.

    records: one dict per processed message with instance, partition, entity,
    seq and finished (time). Returns per-entity details and totals.
    """
    by_entity: Dict[str, List[Dict[str, Any]]] = {}
    for record in sorted(records, key=lambda r: r["finished"]):
        by_entity.setdefault(record["entity"], []).append(record)
    entities: Dict[str, Any] = {}
    total_inversions = 0
    for entity, rows in sorted(by_entity.items()):
        seqs = [row["seq"] for row in rows]
        inversions = sum(1 for a, b in zip(seqs, seqs[1:], strict=False) if b < a)
        total_inversions += inversions
        entities[entity] = {
            "processed_order": seqs,
            "in_order": seqs == sorted(seqs),
            "inversions": inversions,
            "partitions": sorted({row["partition"] for row in rows}),
            "instances": sorted({row["instance"] for row in rows}),
        }
    return {
        "messages_processed": len(records),
        "entities": entities,
        "entities_out_of_order": sum(1 for e in entities.values() if not e["in_order"]),
        "entities_in_more_than_one_partition": sum(
            1 for e in entities.values() if len(e["partitions"]) > 1
        ),
        "total_inversions": total_inversions,
        "all_related_messages_in_order": total_inversions == 0,
    }
