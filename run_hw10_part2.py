"""HW10 Part 2: run questions end to end and score them with the evaluator.

    python run_hw10_part2.py                       three default questions
    python run_hw10_part2.py "your question"      one question

Needs: Kafka (HW8 compose), the three traced agents (python hw10_agents.py ...), Redis
Stack, Ollama (qwen3:8b + nomic-embed-text). Writes reports/hw10/raw/part2_eval.json.
"""

import argparse
import asyncio
import json
import time

from hw10 import config
from hw10.evaluator import evaluate_bundle
from hw10.ingress import TracedIngress
from hw10.logs import run_logged
from hw10.preflight import run_checks
from hw10.runtime import make_cache, make_engine, make_judge

DEFAULT_QUESTIONS = [
    "What is the participant capacity of trial CT-2026-105, and who sponsors it?",
    "Explain in simple words what a Phase II trial is and who can join one.",
    "Which category does trial CT-2026-102 belong to?",
]


def show(record: dict) -> None:
    """Print one evaluator record the way the report shows it."""
    print("-" * 78)
    print(f"trace_id: {record['trace_id']}")
    print(f"question: {record['question'].splitlines()[0]}")
    pq, wh, fh, imp = record["plan_quality"], record["writer_helpfulness"], record["final_helpfulness"], record["improvement"]
    print(f"Plan Quality         : {pq['score']}/5  reason: {pq['reason']}")
    print(f"Writer Helpfulness   : {wh['score']}/5  (trace_id {wh['trace_id']})")
    print(f"Final Answer Helpful.: {fh['score']}/5  final answer: {(fh['final_answer'] or '')[:160]!r}")
    print(f"Final vs Draft       : draft {imp['draft_score']}, final {imp['final_score']}, difference {imp['difference']}")
    print(f"  interpretation: {imp['interpretation']}")
    print(f"evaluator status: {record['status']}  evaluation took {record['evaluation_ms']:.0f} ms")


async def main(questions) -> None:
    """Ask each question, evaluate the joined messages, save everything."""
    if not await run_checks(need_agents=True):
        raise SystemExit(1)
    ingress = TracedIngress(make_cache(), make_engine())
    judge = make_judge()
    records = []
    await ingress.start()
    try:
        for question in questions:
            print(f"\nASK: {question}")
            result = await ingress.ask(question)
            print(f"  -> path={result['path']} status={result['status']} latency={result['latency_ms']:.0f} ms trace_id={result['trace_id']}")
            if result["path"] == "hit":
                print("  served by the semantic cache, no pipeline messages to evaluate; use a new question")
                continue
            if result["bundle"] is None:
                print(f"  no pipeline messages: {result['error']}")
                continue
            record = await asyncio.to_thread(evaluate_bundle, result["bundle"], judge)
            record["review_status"] = result.get("review_status")
            records.append(record)
            show(record)
    finally:
        await ingress.stop()
    out = config.RAW_DIR / "part2_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"created": time.strftime("%Y-%m-%d %H:%M:%S"), "judge_model": config.JUDGE_MODEL, "records": records}, indent=2), encoding="utf-8")
    print(f"\nSaved {len(records)} evaluated trace(s) to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("questions", nargs="*")
    args = parser.parse_args()
    with run_logged("part 2 evaluator"):
        asyncio.run(main(args.questions or DEFAULT_QUESTIONS))
