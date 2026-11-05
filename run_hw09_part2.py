# ruff: noqa: E501
"""Part 2: semantic response cache in front of the HW8 agent pipeline.

    python run_hw09_part2.py [--threshold 0.85] [--keep-cache]

Sends 12 queries (new questions, exact duplicates and paraphrases), logs HIT / MISS
with the similarity score, and reports the hit rate and the measured average
latency of cached and non-cached answers. Saves reports/hw09/raw/part2_results.json.
"""

import argparse
import json
import statistics
import sys

from hw9 import config
from hw9.logs import banner
from hw9.qa_service import QAService
from hw9.runtime import make_everything

# (kind, query): kind is only a note for the report; the cache does not see it.
QUERIES = [
    ("new", "What is the participant capacity of trial CT-2026-101?"),
    ("new", "Which fields are required when creating a trial listing?"),
    ("new", "How long can a trial description be?"),
    ("exact duplicate", "What is the participant capacity of trial CT-2026-101?"),
    ("paraphrase", "What do I have to fill in to create a new trial listing?"),
    ("exact duplicate", "How long can a trial description be?"),
    ("paraphrase", "How many participants can enroll in clinical trial CT-2026-101?"),
    ("new", "How many attempts does an agent make before a message goes to the dead-letter topic?"),
    ("paraphrase", "What is the maximum length of the description of a trial?"),
    ("new (unrelated)", "What is the capital of France?"),
    ("similar, different trial", "What is the participant capacity of trial CT-2026-102?"),
    ("exact duplicate", "How many attempts does an agent make before a message goes to the dead-letter topic?"),
]  # fmt: skip


def mean(values):
    """Average of a list, or None when it is empty."""
    return round(statistics.mean(values), 1) if values else None


def main() -> int:
    """Run the 12 queries and print the summary."""
    parser = argparse.ArgumentParser(description="HW9 Part 2 semantic cache")
    parser.add_argument("--threshold", type=float, default=config.DEFAULT_THRESHOLD)
    parser.add_argument("--keep-cache", action="store_true")
    args = parser.parse_args()

    print(banner("Part 2 semantic cache"))
    cache, agents, engine = make_everything()
    if not args.keep_cache:
        print(f"Cleared {cache.clear()} old cache entries")
    service = QAService(cache, agents, engine, threshold=args.threshold)
    print(
        f"Threshold {args.threshold} | index {config.CACHE_INDEX} | model {config.MODEL_NAME}\n"
    )

    rows = []
    for number, (kind, query) in enumerate(QUERIES, 1):
        print(f"--- Query {number} ({kind}) ---")
        result = service.answer(query)
        print(f"is_cached={result['is_cached']} similarity={result['similarity']:.3f} "
              f"latency_ms={result['latency_ms']}")  # fmt: skip
        print(f"answer: {result['answer'][:200]}\n")
        rows.append({"n": number, "kind": kind, **result})

    cached = [r["latency_ms"] for r in rows if r["is_cached"]]
    fresh = [r["latency_ms"] for r in rows if not r["is_cached"]]
    summary = {
        "threshold": args.threshold,
        "queries": len(rows),
        "hits": len(cached),
        "misses": len(fresh),
        "hit_rate_pct": round(100 * len(cached) / len(rows), 1),
        "avg_latency_cached_ms": mean(cached),
        "avg_latency_not_cached_ms": mean(fresh),
    }
    print("=== Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    (config.RAW_DIR / "part2_results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
