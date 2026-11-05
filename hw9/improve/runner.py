# ruff: noqa: E501
"""Runs questions through the Answering and Evaluator agents (the four variants).

baseline : one answer, no evaluator feedback, no lessons (the evaluator only grades)
repair   : answer -> evaluate -> (REVISE) revise once with the feedback -> evaluate;
           at most MAX_ATTEMPTS = 2 answers, then the system stops and reports
Lessons are switched on by giving the AnsweringAgent a LessonStore.
"""

import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from hw9 import config
from hw9.improve.agents import AnsweringAgent, EvaluatorAgent
from hw9.logs import get_logger

MAX_ATTEMPTS = 2
ALOG = get_logger("ANSWERING")
ELOG = get_logger("EVALUATOR")


def load_questions(name: str) -> List[Dict[str, str]]:
    """Read training / validation / test _data.json (questions only)."""
    return json.loads(
        (config.DATA_DIR / f"{name}_data.json").read_text(encoding="utf-8")
    )


def solve(
    question: str,
    answering: AnsweringAgent,
    evaluator: EvaluatorAgent,
    repair: bool,
    controlled_first: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Answer one question; with repair=True use evaluator feedback (max 2 attempts)."""
    started = time.perf_counter()
    loaded = answering.load_lessons(question)
    if verbose and loaded:
        ALOG.info(
            "loaded lessons %s for: %s", [x["lesson_id"] for x in loaded], question
        )
    attempts: List[Dict[str, Any]] = []
    previous, feedback = "", ""
    limit = MAX_ATTEMPTS if repair else 1
    for number in range(1, limit + 1):
        if number == 1 and controlled_first is not None:
            made = {"answer": controlled_first, "latency_ms": 0.0, "lessons_loaded": []}
            ALOG.info(
                "[CONTROLLED TEST] attempt 1 replaced by an intentionally incomplete answer"
            )
        else:
            made = answering.answer(question, feedback, previous, loaded)
        if verbose:
            ALOG.info("attempt %d -> EVALUATOR: %s", number, made["answer"])
        verdict = evaluator.evaluate(question, made["answer"])
        if verbose:
            ELOG.info(
                "attempt %d -> ANSWERING: %s | %s",
                number,
                verdict.result,
                verdict.explanation,
            )
            if verdict.feedback:
                ELOG.info("feedback: %s", verdict.feedback)
        attempts.append(
            {
                "attempt": number,
                "answer": made["answer"],
                "result": verdict.result,
                "explanation": verdict.explanation,
                "feedback": verdict.feedback,
                "topic": verdict.topic,
                "entry_id": verdict.entry_id,
                "lessons_loaded": [x["lesson_id"] for x in loaded],
                "answer_ms": made["latency_ms"],
            }
        )
        if verdict.passed or not repair:
            break
        previous, feedback = made["answer"], verdict.feedback
    final = attempts[-1]
    return {
        "question": question,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "final_answer": final["answer"],
        "final_result": final["result"],
        "first_result": attempts[0]["result"],
        "topic": attempts[0]["topic"],
        "entry_id": attempts[0]["entry_id"],
        "correct": final["result"] == "PASS",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def run_set(
    questions: List[Dict[str, str]],
    answering: AnsweringAgent,
    evaluator: EvaluatorAgent,
    repair: bool,
    verbose: bool = False,
    label: str = "",
) -> List[Dict[str, Any]]:
    """Run every question of a dataset; keeps the question id."""
    results = []
    for item in questions:
        result = solve(item["question"], answering, evaluator, repair, verbose=verbose)
        result["id"] = item["id"]
        results.append(result)
        mark = "PASS" if result["correct"] else "FAIL"
        print(f"  {label}{item['id']}: {mark} (attempts {result['attempt_count']}, "
              f"{result['latency_ms']} ms)  {item['question']}")  # fmt: skip
    return results


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts and averages for one variant."""
    correct = sum(1 for r in results if r["correct"])
    return {
        "correct": correct,
        "incorrect": len(results) - correct,
        "avg_attempts": round(statistics.mean(r["attempt_count"] for r in results), 2),
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1),
    }


def save(path: Path, data: Any) -> None:
    """Write a JSON result file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
