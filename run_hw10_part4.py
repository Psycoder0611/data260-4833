"""HW10 Part 4: tracing examples and the 50-request latency run.

    python run_hw10_part4.py traces            one cache-miss, one cache-hit and one failed trace
    python run_hw10_part4.py latency --n 50    50 confirmed cache-miss requests (resumable)
    python run_hw10_part4.py hits --n 20       repeat 20 answered questions to get cache-hit latency
    python run_hw10_part4.py summary           p50 / p95 / % table from the saved runs

Needs the same services as Part 2. trace_id is the HW8 correlation_id; spans are written by
the ingress, the three traced agents and the evaluator to reports/hw10/raw/spans.jsonl.
"""

import argparse
import asyncio
import json
import time
from typing import Any, Dict, List

from hw10 import config, stats, tracing
from hw10.evaluator import evaluate_bundle
from hw10.ingress import TracedIngress
from hw10.kafka_trace import FAULT_BAD_PLAN
from hw10.logs import run_logged
from hw10.preflight import run_checks
from hw10.runtime import make_cache, make_engine, make_judge

RUNS_PATH = config.RAW_DIR / "part4_latency_runs.jsonl"
MISS_QUESTION = "What is the participant capacity of trial CT-2026-103, and which category is it in?"
FAILED_QUESTION = "Explain the steps to enroll in a listed trial."


def read_runs() -> List[Dict[str, Any]]:
    """Runs saved so far (resume support)."""
    if not RUNS_PATH.exists():
        return []
    return [json.loads(line) for line in RUNS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def trace_view(trace_id: str) -> List[Dict[str, Any]]:
    """Print the stage table of one trace and return its spans."""
    spans = tracing.group_by_trace(tracing.read_spans())[trace_id]
    print(f"\ntrace_id {trace_id}  path={tracing.trace_path(spans)}  status={tracing.trace_status(spans)}")
    print(f"{'stage':<14}{'start':<30}{'duration ms':>12}  status  error")
    for s in spans:
        print(f"{s['stage']:<14}{s['start']:<30}{s['duration_ms']:>12.1f}  {s['status']:<6}  {s['error'] or ''}")
    return spans


async def one_request(ingress, judge, question: str, evaluate: bool = True, fault=None) -> Dict[str, Any]:
    """Ask, then evaluate if the pipeline ran; returns a run record."""
    result = await ingress.ask(question, fault=fault)
    record = None
    if evaluate and result["bundle"] is not None:
        record = await asyncio.to_thread(evaluate_bundle, result["bundle"], judge)
    return {
        "trace_id": result["trace_id"], "question": question, "path": result["path"],
        "status": result["status"], "error": result["error"], "similarity": result["similarity"],
        "latency_ms": result["latency_ms"], "review_status": result.get("review_status"),
        "review_score": result.get("review_score"), "evaluation": record,
    }


async def traces_cmd(question: str) -> None:
    """Three named traces: miss (success), hit (same question again), failed (injected fault)."""
    if not await run_checks(need_agents=True):
        raise SystemExit(1)
    ingress, judge = TracedIngress(make_cache(), make_engine()), make_judge()
    await ingress.start()
    named: Dict[str, Any] = {}
    try:
        print(f"\n[1] cache MISS, successful: {question}")
        miss = await one_request(ingress, judge, question)
        if miss["path"] != "miss":
            raise SystemExit("That question was already in the cache. Run again with --question 'another question'.")
        named["cache_miss_success"] = {"trace_id": miss["trace_id"], "question": question, "status": miss["status"]}
        trace_view(miss["trace_id"])
        print(f"\n[2] cache HIT, same question again: {question}")
        hit = await one_request(ingress, judge, question, evaluate=False)
        named["cache_hit"] = {"trace_id": hit["trace_id"], "question": question, "status": hit["status"], "similarity": hit["similarity"]}
        trace_view(hit["trace_id"])
        print(f"\n[3] FAILED request (the Planner is told to publish an empty plan): {FAILED_QUESTION}")
        bad = await one_request(ingress, judge, FAILED_QUESTION, fault=FAULT_BAD_PLAN)
        spans = trace_view(bad["trace_id"])
        failing = tracing.failing_stage(spans)
        named["failed"] = {
            "trace_id": bad["trace_id"], "question": FAILED_QUESTION, "status": bad["status"],
            "failing_stage": failing["stage"] if failing else None, "error": failing["error"] if failing else None,
            "how_it_was_made": "inject_fault=bad_plan on the inbox message: the Planner publishes an empty plan, the HW8 Writer rejects it 3 times and the message is dead-lettered",
        }
        print(f"\nFailing stage: {named['failed']['failing_stage']}  error: {named['failed']['error']}")
    finally:
        await ingress.stop()
    out = config.RAW_DIR / "part4_traces.json"
    out.write_text(json.dumps({"created": time.strftime("%Y-%m-%d %H:%M:%S"), "traces": named}, indent=2), encoding="utf-8")
    print(f"\nSaved the three trace ids to {out}")
    for label, info in named.items():
        print(f"  {label}: {info['trace_id']}")


async def latency_cmd(target: int) -> None:
    """Send questions until `target` confirmed cache-miss requests are done."""
    if not await run_checks(need_agents=True):
        raise SystemExit(1)
    pool = json.loads(config.QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    runs = read_runs()
    done_q = {r["question"] for r in runs}
    confirmed = [r for r in runs if r["path"] == "miss" and r["status"] == "ok"]
    print(f"Resuming with {len(confirmed)} confirmed misses already saved." if confirmed else "Starting fresh.")
    ingress, judge = TracedIngress(make_cache(), make_engine()), make_judge()
    await ingress.start()
    skipped = 0
    try:
        for question in pool:
            if len(confirmed) >= target:
                break
            if question in done_q:
                continue
            run = await one_request(ingress, judge, question)
            with open(RUNS_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(run) + "\n")
            if run["path"] == "hit":
                skipped += 1
                print(f"  SKIPPED (served by cache, similarity {run['similarity']:.3f}): {question}")
                continue
            if run["status"] == "ok":
                confirmed.append(run)
            ev = run["evaluation"] or {}
            print(f"[{len(confirmed):>2}/{target}] miss ok={run['status']} sim={run['similarity']:.3f} {run['latency_ms']:.0f} ms "
                  f"plan={ev.get('plan_quality', {}).get('score')} draft={ev.get('writer_helpfulness', {}).get('score')} "
                  f"final={ev.get('final_helpfulness', {}).get('score')}  {question[:50]}")
    finally:
        await ingress.stop()
    print(f"\nconfirmed misses: {len(confirmed)}  skipped because the cache answered: {skipped}")
    if len(confirmed) < target:
        print("The question pool ran out before 50 misses. Clear the s4833 cache or add questions to data/hw10/latency_questions.json.")
    summary_cmd()


async def hits_cmd(count: int) -> None:
    """Ask again 20 questions that were answered and approved: they should hit the cache."""
    if not await run_checks(need_agents=False, need_judge=False):
        raise SystemExit(1)
    again = [r["question"] for r in read_runs() if r["path"] == "miss" and r["status"] == "ok" and r.get("review_status") == "approved"][:count]
    ingress = TracedIngress(make_cache(), make_engine())
    await ingress.start()
    got = 0
    try:
        for question in again:
            result = await ingress.ask(question)
            got += result["path"] == "hit"
            print(f"  {result['path'].upper():<4} sim={result['similarity']:.3f} {result['latency_ms']:.0f} ms  {question[:60]}")
    finally:
        await ingress.stop()
    print(f"\n{got} of {len(again)} repeated questions were cache hits.")


def summary_cmd() -> None:
    """Print and save the p50 / p95 / % table of the confirmed cache-miss requests."""
    runs = [r for r in read_runs() if r["path"] == "miss" and r["status"] == "ok"][:50]
    grouped = tracing.group_by_trace(tracing.read_spans())
    traces = {r["trace_id"]: grouped[r["trace_id"]] for r in runs if r["trace_id"] in grouped}
    table = stats.miss_latency_table(traces)
    similarities = [r["similarity"] for r in runs]
    checks = {
        "requests": len(runs),
        "all_cache_lookup_miss": all(
            any(s["stage"] == "cache_lookup" and not s["attrs"].get("cache_hit") for s in traces[r["trace_id"]]) for r in runs
        ),
        "all_ran_the_full_pipeline": all(
            {"planner", "writer", "reviewer"} <= {s["stage"] for s in traces[r["trace_id"]]} for r in runs
        ),
        "max_similarity": max(similarities) if similarities else None,
        "threshold": config.CACHE_THRESHOLD,
        "approved": sum(r.get("review_status") == "approved" for r in runs),
    }
    dominant = max((r for r in table["rows"] if not r["stage"].startswith("End")), key=lambda r: r["share_pct"] or 0, default=None)
    print(f"\n{'Stage':<32}{'p50 (ms)':>12}{'p95 (ms)':>12}{'% of miss end-to-end':>24}")
    for row in table["rows"]:
        print(f"{row['stage']:<32}{row['p50_ms']:>12}{row['p95_ms']:>12}{row['share_pct']:>24}")
    print(f"\nuser-facing latency (request start -> answer): p50 {table['user_facing_p50_ms']} ms, p95 {table['user_facing_p95_ms']} ms")
    print("checks:", json.dumps(checks))
    if dominant:
        print(f"dominant contributor: {dominant['stage']} ({dominant['share_pct']}%)")
    out = config.RAW_DIR / "part4_latency.json"
    out.write_text(json.dumps({"table": table, "checks": checks, "dominant": dominant}, indent=2), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["traces", "latency", "hits", "summary"])
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--question", default=MISS_QUESTION)
    args = parser.parse_args()
    with run_logged(f"part 4 {args.command}"):
        if args.command == "traces":
            asyncio.run(traces_cmd(args.question))
        elif args.command == "latency":
            asyncio.run(latency_cmd(args.n or 50))
        elif args.command == "hits":
            asyncio.run(hits_cmd(args.n or 20))
        else:
            summary_cmd()
