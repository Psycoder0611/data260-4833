"""HW7 Part 4: build the two Bay Wheels scenario files from the public trip CSV.

The public file has no rider IDs. Each scenario is 600 real trips with one added
column, synthetic_rider_id (seeded, labelled synthetic). Trip values are never
edited. Rider R001 is chosen by rule to be a heavy rider (A) or a light rider (B).

python build_hw07_bike_data.py --raw data/bay_wheels_raw/202609-lyftbikes-tripdata.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from hw7.bike_policy import file_sha256
from hw7.config import RAW_DIR, SEED

ROWS_PER_SCENARIO = 600
TARGET = "R001"
OTHER_RIDERS = 80  # R002 .. R081
OUT_DIR = Path("data") / "bike_scenarios"
FMT = "%Y-%m-%d %H:%M:%S"
RULE = {
    "a": "(45 trips: 30 classic 15-60 min, 15 ebike 10-40 min, over the weeks)",
    "b": "(4 short trips: 3 classic 5-12 min, 1 ebike 5-10 min, different weeks)",
}


def _parse(value: str) -> datetime:
    return datetime.strptime(value[:19], FMT)


def load_pool(raw: str) -> Tuple[List[str], List[List[str]], Dict[str, Any]]:
    """Casual-rider trips with valid times and 0 < duration < 24 h."""
    stats: Dict[str, Any] = Counter()
    pool: List[List[str]] = []
    with open(raw, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}
        for row in reader:
            stats["raw_rows"] += 1
            stats["type:" + row[col["rideable_type"]]] += 1
            if row[col["member_casual"]] != "casual":
                stats["dropped_member"] += 1
                continue
            try:
                minutes = (
                    _parse(row[col["ended_at"]]) - _parse(row[col["started_at"]])
                ).total_seconds() / 60
            except ValueError:
                stats["dropped_bad_time"] += 1
                continue
            if not 0 < minutes < 24 * 60:
                stats["dropped_bad_duration"] += 1
                continue
            pool.append(row)
    stats["eligible_rows"] = len(pool)
    return header, pool, dict(stats)


def classify(row: List[str], col: Dict[str, int]) -> Tuple[str, str, float]:
    minutes = (
        _parse(row[col["ended_at"]]) - _parse(row[col["started_at"]])
    ).total_seconds() / 60
    week = _parse(row[col["started_at"]]).strftime("%W")
    kind = "ebike" if row[col["rideable_type"]].startswith("electric") else "classic"
    return week, kind, minutes


def pick_target(
    scenario: str, pool: List[List[str]], col: Dict[str, int], rng: random.Random
) -> List[int]:
    """Indexes of the rows given to rider R001 (chosen by rule, not edited)."""
    buckets: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for i, row in enumerate(pool):
        week, kind, m = classify(row, col)
        if scenario == "a":
            if kind == "classic" and 15 <= m <= 60:
                buckets[(week, "classic")].append(i)
            elif kind == "ebike" and 10 <= m <= 40:
                buckets[(week, "ebike")].append(i)
        else:
            if kind == "classic" and 5 <= m <= 12:
                buckets[(week, "classic")].append(i)
            elif kind == "ebike" and 5 <= m <= 10:
                buckets[(week, "ebike")].append(i)
    weeks = sorted({w for w, _ in buckets if len(buckets[(w, "classic")]) > 20})
    weeks = [w for w in weeks if buckets[(w, "ebike")]]
    if scenario == "a":
        kinds = ["classic", "classic", "ebike"] * 15
        picks = [(weeks[i % len(weeks)], k) for i, k in enumerate(kinds)]
    else:
        kinds = ["classic", "classic", "classic", "ebike"]
        picks = [(weeks[i % len(weeks)], k) for i, k in enumerate(kinds)]
    chosen: List[int] = []
    for key in picks:
        options = [i for i in buckets[key] if i not in chosen]
        chosen.append(rng.choice(options))
    return chosen


def build(scenario: str, header: List[str], pool: List[List[str]]) -> Dict[str, Any]:
    col = {name: i for i, name in enumerate(header)}
    rng = random.Random(SEED + (0 if scenario == "a" else 1))
    target = pick_target(scenario, pool, col, rng)
    rest = [i for i in range(len(pool)) if i not in set(target)]
    others = rng.sample(rest, ROWS_PER_SCENARIO - len(target))
    owner = {i: TARGET for i in target}
    for i in others:
        owner[i] = f"R{rng.randint(2, OTHER_RIDERS + 1):03d}"
    ordered = sorted(owner, key=lambda i: pool[i][col["started_at"]])
    name = "scenario_a_membership" if scenario == "a" else "scenario_b_payperuse"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(header + ["synthetic_rider_id"])
        for i in ordered:
            writer.writerow(pool[i] + [owner[i]])
    rows = [pool[i] for i in ordered]
    kinds = Counter(classify(r, col)[1] for r in rows)
    weeks = Counter(classify(r, col)[0] for r in rows)
    mine = [pool[i] for i in target]
    return {
        "label": name,
        "path": str(path),
        "rows": len(rows),
        "riders": len(set(owner.values())),
        "target_rider": TARGET,
        "target_rides": len(target),
        "target_kinds": dict(Counter(classify(r, col)[1] for r in mine)),
        "bike_types_in_file": dict(Counter(r[col["rideable_type"]] for r in rows)),
        "rows_per_week": dict(sorted(weeks.items())),
        "rows_missing_station_name": sum(
            1 for r in rows if not r[col["start_station_name"]]
        ),
        "sha256": file_sha256(str(path)),
        "kinds": dict(kinds),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    args = ap.parse_args()
    header, pool, stats = load_pool(args.raw)
    raw_hash = file_sha256(args.raw)
    for scenario in ("a", "b"):
        info = build(scenario, header, pool)
        info["source_file"] = Path(args.raw).name
        info["source_sha256"] = raw_hash
        info["source_filter_counts"] = stats
        info["seed"] = SEED + (0 if scenario == "a" else 1)
        info["construction"] = (
            "Real casual-rider trips from the public file, values unchanged. "
            "synthetic_rider_id is added: R001 gets rows chosen by rule "
            + RULE[scenario]
            + "; every other row gets a random id R002-R081."
        )
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        out = RAW_DIR / f"bike_{info['label']}_trip_summary.json"
        out.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        print(
            f"{info['label']}: {info['rows']} rows, {info['riders']} riders, "
            f"R001 has {info['target_rides']} rides -> {info['path']}"
        )
        print(f"   sha256 {info['sha256']}")
    print(f"source sha256 {raw_hash}")
    print(f"filter counts {stats}")


if __name__ == "__main__":
    main()
