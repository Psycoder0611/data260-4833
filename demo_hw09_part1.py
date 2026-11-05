# ruff: noqa: E501
"""Part 1 demo: the Redis view counter with a database sync every 10 accesses.

    python demo_hw09_part1.py [--trial-code CT-2026-101] [--accesses 25]

Resets the counter and the stored view_count of the chosen trial first, so the
output always starts at Access #1.
"""

import argparse
import json
import sys

import redis

from hw9 import config, db
from hw9.cache_db import ClinicalTrialCache
from hw9.logs import banner


def main() -> int:
    """Run the demo and save the result to reports/hw09/raw/part1_counter.json."""
    parser = argparse.ArgumentParser(description="HW9 Part 1 view counter demo")
    parser.add_argument("--trial-code", default="CT-2026-101")
    parser.add_argument("--accesses", type=int, default=25)
    args = parser.parse_args()

    print(banner("Part 1 view counter"))
    client = redis.Redis(
        host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
    )
    client.ping()
    cache = ClinicalTrialCache(client)
    trial = db.get_trial_by_code(cache.engine, args.trial_code)
    if trial is None:
        print(f"Trial {args.trial_code} not found in the database")
        return 1
    trial_id = trial["id"]
    client.delete(cache.views_key(trial_id))
    db.set_view_count(cache.engine, trial_id, 0)
    print(
        f"Trial {args.trial_code} (id {trial_id}), Redis key {cache.views_key(trial_id)}"
    )

    print("\n=== Testing Counter ===\n")
    lines = []
    for i in range(1, args.accesses + 1):
        total = cache.increment_clinical_trial_views(trial_id)
        print(f"Access #{i}: Total = {total}")
        synced = total % config.SYNC_EVERY == 0
        if synced:
            print("✓ Synced views to database")
        lines.append({"access": i, "total": total, "synced": synced})

    stored = db.get_view_count(cache.engine, trial_id)
    redis_value = int(client.get(cache.views_key(trial_id)))
    print(f"\nRedis counter: {redis_value} | database view_count: {stored}")
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    (config.RAW_DIR / "part1_counter.json").write_text(
        json.dumps(
            {
                "trial_code": args.trial_code,
                "trial_id": trial_id,
                "redis_key": cache.views_key(trial_id),
                "accesses": lines,
                "redis_value": redis_value,
                "database_view_count": stored,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
