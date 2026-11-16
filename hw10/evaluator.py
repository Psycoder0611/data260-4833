# ruff: noqa: E501
"""Evaluator for the Planner / Writer / Reviewer pipeline (Part 2).

Input: one joined trace (plan, draft and final messages with the same correlation_id,
exactly as they were read from Kafka). Output, one record per trace:

  plan_quality          score 1-5 + brief reason          (judge reads question + plan)
  writer_helpfulness    score 1-5 + trace_id + reason     (judge reads question + draft)
  final_helpfulness     score 1-5 + the final answer      (judge reads question + final)
  improvement           draft score, final score, difference and an interpretation

All scores use the same 1-5 scale as the human labels in Part 3. The evaluation is
bounded: a malformed or incomplete message gives status "invalid_input" for the
metrics that need it, and an unavailable judge gives "judge_error"/"timeout" for
the metric that hit it; the other metrics still run and the call always returns.
"""

import time
from typing import Any, Dict, Optional

from hw10 import config, tracing
from hw10.judge import plan_to_text, score_text

COMPONENT = "EVALUATOR"


def _value(bundle: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    """The decoded message of one role, or None."""
    row = bundle.get(role)
    value = row.get("value") if isinstance(row, dict) else None
    return value if isinstance(value, dict) and "_malformed" not in value else None


def interpret(draft: Dict[str, Any], final: Dict[str, Any], same_text: bool, review: Dict[str, Any]) -> str:
    """One or two sentences saying what the draft-to-final difference means."""
    if draft["score"] is None or final["score"] is None:
        return "Not comparable: at least one of the two scores is missing (see status)."
    diff = final["score"] - draft["score"]
    status = review.get("status")
    score = review.get("score")
    if same_text:
        base = (
            "The final answer is word for word the Writer's draft: the Reviewer only approved or "
            f"rejected it (status {status}, reviewer score {score}/10) and did not edit it, "
            "so no improvement is possible by design."
        )
        if diff == 0:
            return base + " The two scores are equal, as expected."
        return base + f" The judge still gave different scores ({diff:+d}), which is judge noise."
    if diff > 0:
        return f"The final answer scored {diff} point(s) higher than the draft: the Reviewer stage improved it."
    if diff < 0:
        return f"The final answer scored {-diff} point(s) lower than the draft: the Reviewer stage made it worse."
    return "The final answer differs from the draft but scored the same: no measurable improvement."


def evaluate_bundle(
    bundle: Dict[str, Any],
    judge: Any,
    span_path=None,
    write_span: bool = True,
    metric_timeout: float = config.METRIC_TIMEOUT,
) -> Dict[str, Any]:
    """Evaluate one joined trace; always returns a record, never raises."""
    trace_id = bundle.get("trace_id", "unknown")
    started = time.time()
    plan_msg = _value(bundle, "plan")
    draft_msg = _value(bundle, "draft")
    final_msg = _value(bundle, "final")
    question = ""
    for msg in (plan_msg, draft_msg, final_msg):
        if msg and isinstance(msg.get("question"), str) and msg["question"].strip():
            question = msg["question"]
            break

    missing = lambda what: {  # noqa: E731
        "score": None, "reason": "", "status": "invalid_input",
        "error": f"{what} message missing or malformed", "judge_score_0_10": None,
    }

    plan = plan_msg.get("plan") if plan_msg else None
    if isinstance(plan, list) and plan and all(isinstance(s, str) for s in plan):
        plan_res = score_text("plan_quality", question, plan_to_text(plan), judge, metric_timeout)
    else:
        plan_res = missing("plan")
    draft_text = draft_msg.get("draft") if draft_msg else None
    draft_res = (
        score_text("helpfulness", question, draft_text, judge, metric_timeout)
        if isinstance(draft_text, str) and draft_text.strip()
        else missing("draft")
    )
    final_text = final_msg.get("answer") if final_msg else None
    final_res = (
        score_text("helpfulness", question, final_text, judge, metric_timeout)
        if isinstance(final_text, str) and final_text.strip()
        else missing("final")
    )
    same_text = bool(draft_text) and draft_text == final_text
    review = {"status": (final_msg or {}).get("status"), "score": (final_msg or {}).get("score")}
    diff = (
        final_res["score"] - draft_res["score"]
        if final_res["score"] is not None and draft_res["score"] is not None
        else None
    )
    results = (plan_res, draft_res, final_res)
    errors = [r["error"] for r in results if r["status"] != "ok"]
    status = "ok" if not errors else ("error" if all(r["status"] != "ok" for r in results) else "partial")
    record = {
        "trace_id": trace_id,
        "question": question,
        "plan_quality": {"score": plan_res["score"], "reason": plan_res["reason"],
                         "status": plan_res["status"], "error": plan_res["error"],
                         "judge_score_0_10": plan_res["judge_score_0_10"], "plan": plan},
        "writer_helpfulness": {"score": draft_res["score"], "trace_id": trace_id,
                               "reason": draft_res["reason"], "status": draft_res["status"],
                               "error": draft_res["error"], "judge_score_0_10": draft_res["judge_score_0_10"], "draft": draft_text},
        "final_helpfulness": {"score": final_res["score"], "final_answer": final_text,
                              "reason": final_res["reason"], "status": final_res["status"],
                              "error": final_res["error"], "judge_score_0_10": final_res["judge_score_0_10"]},
        "improvement": {"draft_score": draft_res["score"], "final_score": final_res["score"],
                        "difference": diff, "same_text": same_text,
                        "interpretation": interpret(draft_res, final_res, same_text, review)},
        "reviewer": review,
        "pipeline_issues": bundle.get("issues", []),
        "status": status,
        "errors": errors,
        "judge_model": config.JUDGE_MODEL,
        "evaluation_ms": round((time.time() - started) * 1000, 1),
    }
    if write_span and trace_id != "unknown":
        tracing.record(
            trace_id, tracing.EVALUATION, started, time.time(),
            "ok" if status == "ok" else "error",
            None if status == "ok" else "; ".join(errors)[:300],
            COMPONENT, {"status": status}, span_path,
        )
    return record
