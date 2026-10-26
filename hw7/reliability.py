"""Part 2 reliability measurement: run the fixed cases many times and summarize."""

import json
import time
from typing import Any, Callable, Dict, List, Optional

from hw7 import agent, cases, config, llm

LOST_CHAIN = agent.LOST_CHAIN
FAILURE_CLASSES = [
    agent.MALFORMED,
    agent.UNKNOWN_TOOL,
    agent.TEXT_INSTEAD,
    LOST_CHAIN,
]


class FaultInjector:
    """Corrupts every Nth tool-call reply from the model (labeled test only).

    Kinds rotate: unknown tool name, bad argument type, plain text. Repair
    replies are never corrupted, so the model has to fix the bad call itself.
    """

    BAD_ARGS = {
        "search_trials": {"query": 123},
        "get_trial_details": {"trial_id": "abc"},
        "organization_trial_summary": {"organization_id": "two"},
    }

    def __init__(self, every: int):
        self.every = every
        self.seen = 0
        self.injected = 0

    def maybe_corrupt(self, messages, content: str) -> str:
        if not self.every or messages[-1]["content"].startswith("Your last reply"):
            return content
        decision = agent.parse_decision(content)
        if not decision or decision.get("action") != "tool":
            return content
        self.seen += 1
        if self.seen % self.every:
            return content
        kind = self.injected % 3
        self.injected += 1
        if kind == 0:
            decision["tool"] = "find_trials"
        elif kind == 1:
            decision["inputs"] = dict(self.BAD_ARGS.get(decision.get("tool"), {"x": 1}))
        else:
            return "I think the answer is probably in the trial database."
        return json.dumps(decision)


def run_attempt(
    case: Dict[str, Any],
    attempt: int,
    seed: int,
    temperature: float,
    chat_impl: Callable[..., Dict[str, Any]] = llm.chat,
    log_path=config.TOOL_LOG_PATH,
    injector: Optional[FaultInjector] = None,
) -> Dict[str, Any]:
    """Run one attempt of one case and return a flat result row."""
    latency = {"ms": 0.0}

    def chat_fn(messages):
        reply = chat_impl(messages, temperature=temperature, seed=seed)
        latency["ms"] += reply.get("latency_ms", 0.0)
        if injector:
            reply = dict(reply)
            reply["content"] = injector.maybe_corrupt(messages, reply["content"])
        return reply

    injected_before = injector.injected if injector else 0

    started = time.perf_counter()
    result = agent.run_agent(
        case["prompt"],
        chat_fn=chat_fn,
        log_path=log_path,
        run_id=f"rel-{attempt:02d}-{case['id']}",
    )
    chain = cases.chain_ok(case, result["tool_log"])
    return {
        "attempt": attempt,
        "case": case["id"],
        "seed": seed,
        "temperature": temperature,
        "call_attempts": result["call_attempts"],
        "first_try_ok": result["first_try_ok"],
        "repair_attempts": result["repair_attempts"],
        "repair_ok": result["repair_ok"],
        "failures": result["failures"],
        "injected": (injector.injected - injected_before) if injector else 0,
        "tool_calls": result["tool_calls"],
        "chain_ok": chain,
        "answer_ok": chain and cases.answer_ok(case, result["answer"]),
        "stop_reason": result["stop_reason"],
        "iterations": result["iterations"],
        "tokens": result["input_tokens"] + result["output_tokens"],
        "model_latency_ms": round(latency["ms"], 1),
        "wall_ms": round((time.perf_counter() - started) * 1000, 1),
        "answer": result["answer"],
        "tool_log": result["tool_log"],
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Well-formed call rate before/after repair, failures by class, chain stats."""
    calls = sum(r["call_attempts"] for r in rows)
    first = sum(r["first_try_ok"] for r in rows)
    repaired = sum(r["repair_ok"] for r in rows)
    failure_counts = {name: 0 for name in FAILURE_CLASSES}
    for row in rows:
        for name in row["failures"]:
            failure_counts[name] = failure_counts.get(name, 0) + 1
    failure_counts[LOST_CHAIN] = sum(1 for r in rows if not r["chain_ok"])
    by_case = {}
    for case_id in sorted({r["case"] for r in rows}):
        subset = [r for r in rows if r["case"] == case_id]
        by_case[case_id] = {
            "attempts": len(subset),
            "chain_ok": sum(1 for r in subset if r["chain_ok"]),
            "answer_ok": sum(1 for r in subset if r["answer_ok"]),
        }
    return {
        "attempts": len(rows),
        "tool_call_attempts": calls,
        "faults_injected": sum(r.get("injected", 0) for r in rows),
        "well_formed_before_repair": first,
        "well_formed_after_repair": first + repaired,
        "rate_before_repair": _rate(first, calls),
        "rate_after_repair": _rate(first + repaired, calls),
        "failures_by_class": failure_counts,
        "chains_completed": sum(1 for r in rows if r["chain_ok"]),
        "answers_correct": sum(1 for r in rows if r["answer_ok"]),
        "by_case": by_case,
        "avg_tool_calls": round(sum(r["tool_calls"] for r in rows) / len(rows), 2)
        if rows
        else 0,
        "total_tokens": sum(r["tokens"] for r in rows),
        "avg_model_latency_ms": round(
            sum(r["model_latency_ms"] for r in rows) / len(rows), 1
        )
        if rows
        else 0,
    }
