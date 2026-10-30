# ruff: noqa: E501
"""Build reports/hw08/METRICS.md from the raw files saved by the HW8 runs.

Reads whatever exists in reports/hw08/raw/ and leaves a clear "not run yet"
line for anything missing, so the file is honest at every stage.

  raw/jmeter_kafka.csv, raw/jmeter_direct.csv   JMeter listener / JTL exports
  raw/part3_duplicate|death|poison.json         failure scenarios
  raw/part3_ordering.json                       ordering scenario

Run:  python make_hw08_metrics.py
"""

import json
from typing import Any, Dict, List, Optional

from hw8 import config, jtl

RAW = config.RAW_DIR
OUT = config.REPORT_DIR / "METRICS.md"


def load(name: str) -> Optional[Dict[str, Any]]:
    """Load a raw JSON file, or None if it is missing."""
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def table(headers: List[str], rows: List[List[Any]]) -> str:
    """A GitHub-style markdown table."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def jmeter_section() -> str:
    """Kafka endpoint versus direct endpoint, from the JMeter exports."""
    parts = [
        "## JMeter: Kafka endpoint vs direct endpoint (100 threads, 10 s ramp-up, 1 loop)\n"
    ]
    rows = []
    for label, name in (
        ("Kafka (request/response)", "jmeter_kafka.csv"),
        ("Direct (no Kafka)", "jmeter_direct.csv"),
    ):
        path = RAW / name
        if not path.exists():
            rows.append([label, "not run yet", "", "", "", "", "", "", ""])
            continue
        s = jtl.summarize(path)
        rows.append(
            [
                label,
                s["samples"],
                s["average_ms"],
                s["min_ms"],
                s["max_ms"],
                s["p90_ms"],
                s["p95_ms"],
                f"{s['error_pct']}%",
                s["throughput_per_sec"]
                if s["throughput_per_sec"] is not None
                else "n/a",
            ]
        )
    headers = [
        "Endpoint",
        "Samples",
        "Avg (ms)",
        "Min (ms)",
        "Max (ms)",
        "p90 (ms)",
        "p95 (ms)",
        "Error %",
        "Throughput (req/s)",
    ]
    parts.append(table(headers, rows))
    return "\n".join(parts)


def failure_section() -> str:
    """Before/after evidence for the three failure modes."""
    out = ["## Part 3 failure table (before vs after)\n"]
    rows = []
    dup = load("part3_duplicate.json")
    if dup:
        rows.append(
            [
                "Duplicate delivery",
                "idempotency off",
                f"{dup['before']['drafts_produced']} drafts for 1 request",
                "idempotency on",
                f"{dup['after']['drafts_produced']} draft, {dup['after']['duplicates_skipped']} duplicate skipped",
            ]
        )
    else:
        rows.append(["Duplicate delivery", "", "not run yet", "", ""])
    death = load("part3_death.json")
    if death:
        b, a = death["before"], death["after"]
        rows.append(
            [
                "Consumer dies mid-work",
                "commit on receive",
                f"redelivered={b['victim_redelivered_after_restart']}, draft produced={b['victim_draft_produced']}",
                "commit after success",
                f"redelivered={a['victim_redelivered_after_restart']}, draft produced={a['victim_draft_produced']}",
            ]
        )
    else:
        rows.append(["Consumer dies mid-work", "", "not run yet", "", ""])
    poison = load("part3_poison.json")
    if poison:
        b, a = poison["before"], poison["after"]
        rows.append(
            [
                "Poison message",
                "unbounded retry, no DLQ",
                f"{b['failed_attempts']} attempts seen, next message processed={b['good_message_processed']}",
                f"max {config.MAX_ATTEMPTS} attempts + dead letter",
                f"{a['failed_attempts']} attempts, {len(a['dead_letter_messages'])} in dead letter, next message processed={a['good_message_processed']}",
            ]
        )
    else:
        rows.append(["Poison message", "", "not run yet", "", ""])
    out.append(
        table(
            [
                "Failure",
                "Before (fix off)",
                "Before: evidence",
                "After (fix on)",
                "After: evidence",
            ],
            rows,
        )
    )
    return "\n".join(out)


def ordering_section() -> str:
    """Ordering with and without an entity key."""
    out = [
        "## Ordering (20 VERIFY_SEED messages, 2 partitions, 2 Writers in one group)\n"
    ]
    data = load("part3_ordering.json")
    if not data:
        return "\n".join(out + ["not run yet"])
    rows = []
    for mode, label in (("unkeyed", "No key"), ("keyed", "Key = entity")):
        a = data[mode]["analysis"]
        rows.append(
            [
                label,
                a["messages_processed"],
                a["total_inversions"],
                a["entities_out_of_order"],
                a["entities_in_more_than_one_partition"],
            ]
        )
    out.append(
        table(
            [
                "Run",
                "Processed",
                "Order inversions",
                "Entities out of order",
                "Entities split over partitions",
            ],
            rows,
        )
    )
    return "\n".join(out)


def main() -> None:
    """Write METRICS.md."""
    text = "\n\n".join([
        f"# HW8 metrics (SID4 {config.SID4}, seed {config.SEED}, verify seed {config.VERIFY_SEED})\n",
        jmeter_section(), failure_section(), ordering_section(),
    ]) + "\n"  # fmt: skip
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
