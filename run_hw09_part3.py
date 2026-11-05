# ruff: noqa: E501
"""Part 3: threshold sweep, one false hit in full, and stale-answer invalidation.

    python run_hw09_part3.py agents            # run the HW8 agents once per distinct query
    python run_hw09_part3.py sweep             # 40 cases x 5 thresholds (3.2) + cost (3.4)
    python run_hw09_part3.py falsehit          # one false hit in full (3.3)
    python run_hw09_part3.py stale             # stale answer + invalidation (3.5)

Why `agents` is separate: a cache miss runs three local model calls (slow). Each
distinct query is run through the agents once and its answer and latency are
recorded. The sweep then uses real Redis lookups and real embedding calls for every
threshold, and for a miss it adds the recorded agent latency instead of running the
agents again (the answer to a query does not depend on the threshold). The cache is
read-only during the sweep: it holds only the 10 seed answers.
"""

import argparse
import json
import re
import statistics
import sys
import time
from typing import Any, Dict, List

import yaml

from hw9 import config, db, facts
from hw9.agent_backend import HW8Agents
from hw9.logs import banner
from hw9.qa_service import QAService
from hw9.runtime import make_cache

ANSWERS_PATH = config.RAW_DIR / "part3_agent_answers.json"
SWEEP_PATH = config.RAW_DIR / "part3_sweep.json"


def load_cases() -> Dict[str, Any]:
    """Read cache_cases.yaml (never edited after the first run)."""
    return yaml.safe_load(config.CASES_PATH.read_text(encoding="utf-8"))


def save_json(path, data) -> None:
    """Write JSON next to the other raw files."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_json(path) -> Any:
    """Read a JSON file, or None."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def distinct_queries(spec: Dict[str, Any]) -> List[str]:
    """Seed queries first, then every case query that is not a seed already."""
    queries = [s["query"] for s in spec["seed_queries"]]
    for case in spec["cases"]:
        if case["query"] not in queries:
            queries.append(case["query"])
    return queries


# ------------------------------------------------------------------ agents
def cmd_agents(_args) -> int:
    """Run the HW8 agents once for every distinct query and record the result."""
    print(banner("Part 3 agent answers"))
    spec = load_cases()
    engine = db.make_engine()
    agents = HW8Agents()
    done = load_json(ANSWERS_PATH) or {}
    queries = distinct_queries(spec)
    for number, query in enumerate(queries, 1):
        if query in done:
            print(f"[{number}/{len(queries)}] already recorded: {query}")
            continue
        facts_text, version, entity = facts.facts_for(engine, query)
        run = agents.run(query, facts_text)
        done[query] = {**run, "data_version": version, "entity": entity}
        print(
            f"[{number}/{len(queries)}] {run['agent_ms']} ms, score {run['score']}: {query}"
        )
        save_json(ANSWERS_PATH, done)
    print(f"Recorded {len(done)} answers in {ANSWERS_PATH}")
    return 0


# ------------------------------------------------------------------- sweep
def run_threshold(cache, spec, answers, threshold: float) -> Dict[str, Any]:
    """Evaluate all 40 cases at one threshold against a cache holding only the seeds."""
    rows = []
    for case in spec["cases"]:
        started = time.perf_counter()
        vector = cache.embed(case["query"])
        hit = cache.lookup(case["query"], embedding=vector)
        cache_ms = (time.perf_counter() - started) * 1000
        similarity = hit.similarity if hit else 0.0
        is_hit = bool(hit and similarity >= threshold)
        agent_ms = 0.0 if is_hit else answers[case["query"]]["agent_ms"]
        rows.append(
            {
                "id": case["id"],
                "type": case["type"],
                "query": case["query"],
                "expected_hit": case["expected_hit"],
                "hit": is_hit,
                "similarity": similarity,
                "matched_query": hit.query if hit else None,
                "cached_answer": hit.answer if hit else None,
                "latency_ms": round(cache_ms + agent_ms, 1),
            }
        )
    hits = [r for r in rows if r["hit"]]
    should_miss = [r for r in rows if not r["expected_hit"]]
    false_hits = [r for r in rows if r["hit"] and not r["expected_hit"]]
    missed_hits = [r for r in rows if not r["hit"] and r["expected_hit"]]
    misses = len(rows) - len(hits)
    return {
        "threshold": threshold,
        "hit_rate_pct": round(100 * len(hits) / len(rows), 1),
        "false_hit_rate_pct": round(100 * len(false_hits) / len(should_miss), 1),
        "false_hits": len(false_hits),
        "missed_hits": len(missed_hits),
        "misses": misses,
        "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows), 1),
        "total_cost": round(
            misses * config.COST_MISS + len(false_hits) * config.COST_FALSE_HIT, 2
        ),
        "rows": rows,
    }


def cmd_sweep(_args) -> int:
    """Fill the cache with the seeds, then sweep the five thresholds."""
    print(banner("Part 3 threshold sweep"))
    spec = load_cases()
    answers = load_json(ANSWERS_PATH)
    if not answers or any(q not in answers for q in distinct_queries(spec)):
        print("Run `python run_hw09_part3.py agents` first")
        return 1
    cache = make_cache()
    cache.clear()
    for seed in spec["seed_queries"]:
        recorded = answers[seed["query"]]
        cache.store(
            seed["query"],
            recorded["answer"],
            data_version=recorded["data_version"],
            entity=recorded["entity"],
        )
    print(f"Cache holds {cache.size()} seed answers; cost model: miss ${config.COST_MISS}, "
          f"false hit ${config.COST_FALSE_HIT}\n")  # fmt: skip
    results = [run_threshold(cache, spec, answers, t) for t in config.THRESHOLDS]
    header = f"{'Threshold':>9} {'Hit rate':>9} {'False-hit':>10} {'Missed hits':>12} {'Mean ms':>9} {'Total cost':>11}"
    print(header)
    for r in results:
        print(f"{r['threshold']:>9.2f} {r['hit_rate_pct']:>8.1f}% {r['false_hit_rate_pct']:>9.1f}% "
              f"{r['missed_hits']:>12} {r['mean_latency_ms']:>9.1f} {r['total_cost']:>11.2f}")  # fmt: skip
    save_json(
        SWEEP_PATH,
        {
            "cost_miss": config.COST_MISS,
            "cost_false_hit": config.COST_FALSE_HIT,
            "results": results,
        },
    )
    best = min(results, key=lambda r: (r["total_cost"], -r["threshold"]))
    print(
        f"\nLowest total cost: threshold {best['threshold']:.2f} (${best['total_cost']})"
    )
    return 0


# --------------------------------------------------------------- false hit
def words(text: str) -> set:
    """Lower-case word set of a query."""
    return set(re.findall(r"[a-z0-9\-]+", text.lower()))


def cmd_falsehit(args) -> int:
    """Show the highest-similarity false hit at the chosen threshold in full."""
    print(banner("Part 3 one false hit in full"))
    sweep = load_json(SWEEP_PATH)
    answers = load_json(ANSWERS_PATH)
    if not sweep:
        print("Run the sweep first")
        return 1
    result = next(
        r for r in sweep["results"] if abs(r["threshold"] - args.threshold) < 1e-9
    )
    bad = sorted(
        (r for r in result["rows"] if r["hit"] and not r["expected_hit"]),
        key=lambda r: -r["similarity"],
    )
    if not bad:
        print(f"No false hit at threshold {args.threshold}; try a lower one")
        return 1
    case = bad[0]
    own = answers[case["query"]]
    print(f"Threshold: {args.threshold}   Case: {case['id']} ({case['type']})\n")
    print(f"Cached query   : {case['matched_query']}")
    print(f"Incoming query : {case['query']}")
    print(f"Similarity     : {case['similarity']}\n")
    print(f"Cached answer returned:\n  {case['cached_answer']}\n")
    print(f"Correct answer (HW8 agents on the incoming query):\n  {own['answer']}\n")
    only_cached = sorted(words(case["matched_query"]) - words(case["query"]))
    only_new = sorted(words(case["query"]) - words(case["matched_query"]))
    print(f"Words only in the cached query  : {only_cached}")
    print(f"Words only in the incoming query: {only_new}")
    save_json(
        config.RAW_DIR / "part3_false_hit.json",
        {
            "threshold": args.threshold,
            "case": case,
            "correct_answer": own["answer"],
            "words_only_in_cached": only_cached,
            "words_only_in_incoming": only_new,
        },
    )
    return 0


# -------------------------------------------------------------------- stale
STALE_QUERY = "What is the participant capacity of trial CT-2026-101?"
STALE_CODE = "CT-2026-101"
STALE_NEW_CAPACITY = 120


def cmd_stale(_args) -> int:
    """3.5: update a record, show the stale hit, then the version-marker invalidation."""
    print(banner("Part 3.5 stale answers and invalidation"))
    cache = make_cache()
    engine = db.make_engine()
    agents = HW8Agents()
    row = db.get_trial_by_code(engine, STALE_CODE)
    if row is None:
        print(f"{STALE_CODE} not found in s4833_rel.clinical_trials")
        return 1
    original = row["participant_capacity"]
    log: Dict[str, Any] = {
        "query": STALE_QUERY,
        "trial_code": STALE_CODE,
        "original": original,
    }
    cache.clear()
    try:
        print(f"\n[1] Database: {STALE_CODE} participant_capacity = {original}")
        plain = QAService(cache, agents, engine, check_version=False)
        first = plain.answer(STALE_QUERY)
        print(f"    first ask  -> cached={first['is_cached']}: {first['answer'][:160]}")
        log["first"] = first
        again = plain.answer(STALE_QUERY)
        print(f"    second ask -> cached={again['is_cached']}: {again['answer'][:160]}")

        print(f"\n[2] UPDATE clinical_trials SET participant_capacity = {STALE_NEW_CAPACITY} "
              f"WHERE trial_code = '{STALE_CODE}'")  # fmt: skip
        db.update_capacity(engine, STALE_CODE, STALE_NEW_CAPACITY)
        now = db.get_trial_by_code(engine, STALE_CODE)["participant_capacity"]
        print(f"    database now says {now}")
        log["updated_to"] = now

        print("\n[3] Same question, NO invalidation: stale hit")
        stale = plain.answer(STALE_QUERY)
        print(
            f"    cached={stale['is_cached']} similarity={stale['similarity']}: {stale['answer'][:160]}"
        )
        log["stale_hit"] = stale

        print("\n[4] Same question, version-marker check ON")
        fixed = QAService(cache, agents, engine, check_version=True)
        fresh = fixed.answer(STALE_QUERY)
        print(
            f"    cached={fresh['is_cached']} invalidated={fresh['invalidated']}: {fresh['answer'][:160]}"
        )
        log["after_invalidation"] = fresh
        warm = fixed.answer(STALE_QUERY)
        print(f"    next ask -> cached={warm['is_cached']}: {warm['answer'][:160]}")
        log["warm_hit"] = warm
    finally:
        db.update_capacity(engine, STALE_CODE, original)
        cache.clear()
        print(
            f"\nRestored {STALE_CODE} participant_capacity = {original} and cleared the cache"
        )
    save_json(config.RAW_DIR / "part3_stale.json", log)
    return 0


def main() -> int:
    """Dispatch the sub-command."""
    parser = argparse.ArgumentParser(description="HW9 Part 3")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("agents").set_defaults(fn=cmd_agents)
    sub.add_parser("sweep").set_defaults(fn=cmd_sweep)
    fh = sub.add_parser("falsehit")
    fh.add_argument("--threshold", type=float, default=config.DEFAULT_THRESHOLD)
    fh.set_defaults(fn=cmd_falsehit)
    sub.add_parser("stale").set_defaults(fn=cmd_stale)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
