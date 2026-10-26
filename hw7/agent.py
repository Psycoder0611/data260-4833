"""HW7 Part 2: hand-written agent loop over the three HW5 domain tools.

The model replies with JSON text (the HW5 pattern). Each reply is checked
before any tool runs. A bad reply gets one repair prompt that names the exact
problem; too many failed repairs stop the run cleanly.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hw7 import config, llm
from tool_executor import execute_tool

SYSTEM_PROMPT = """You are a Clinical Trial Listings agent.
You have exactly three tools:
1. search_trials         inputs: {"query": string, "limit": integer 1-25 (optional)}
2. get_trial_details     inputs: {"trial_id": positive integer}
3. organization_trial_summary  inputs: {"organization_id": positive integer}

Reply with ONLY one JSON object per turn.
To call a tool: {"action": "tool", "tool": "<name>", "inputs": {...}}
To finish: {"action": "final", "answer": "<your answer>"}

Notes: search_trials only matches words in trial titles and trial codes (it
cannot filter by organization) and returns short summaries. For the full details
of a trial, call get_trial_details with its id. Use limit 5 or more unless asked.

Tool results come back as tool messages. Always use the tools to get facts
and never invent trial data. Use as many tool calls as the question needs,
one per turn, then give the final answer. If a tool returns an error,
explain it clearly in the final answer."""

# The first-draft prompt (before the two clarifying sentences were added); the
# Part 3 comparison also runs on it so the loops have real mistakes to fix.
_NOTES_START = SYSTEM_PROMPT.index("Notes: search_trials")
_NOTES_END = SYSTEM_PROMPT.index("Tool results come back")
DRAFT_SYSTEM_PROMPT = SYSTEM_PROMPT[:_NOTES_START] + SYSTEM_PROMPT[_NOTES_END:]

# Schema for each tool: field -> (type, required, minimum, maximum)
TOOL_SCHEMAS: Dict[str, Dict[str, tuple]] = {
    "search_trials": {
        "query": (str, True, None, None),
        "limit": (int, False, 1, 25),
    },
    "get_trial_details": {"trial_id": (int, True, 1, None)},
    "organization_trial_summary": {"organization_id": (int, True, 1, None)},
}

# Failure classes used in the reliability table
MALFORMED = "malformed_arguments"
UNKNOWN_TOOL = "unknown_tool"
TEXT_INSTEAD = "text_when_tool_required"
LOST_CHAIN = "lost_multi_step_chain"


class Problem:
    """What is wrong with a model reply (kind is one of the failure classes)."""

    def __init__(self, kind: str, message: str):
        self.kind = kind
        self.message = message

    def __repr__(self) -> str:
        return f"Problem({self.kind!r}, {self.message!r})"


def parse_decision(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of the reply (handles code fences/prose)."""
    text = (text or "").strip()
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        return obj if isinstance(obj, dict) else None
    return None


def validate_inputs(tool: str, inputs: Any) -> Optional[str]:
    """Return a specific message if inputs break the tool's schema, else None."""
    if not isinstance(inputs, dict):
        return "inputs must be a JSON object"
    schema = TOOL_SCHEMAS[tool]
    for field in inputs:
        if field not in schema:
            return f"unexpected field '{field}'; allowed fields: {sorted(schema)}"
    for field, (ftype, required, low, high) in schema.items():
        if field not in inputs:
            if required:
                return f"missing required field '{field}'"
            continue
        value = inputs[field]
        if ftype is int and (isinstance(value, bool) or not isinstance(value, int)):
            return f"'{field}' must be an integer, got {type(value).__name__}"
        if ftype is str and not isinstance(value, str):
            return f"'{field}' must be a string, got {type(value).__name__}"
        if ftype is str and not value.strip():
            return f"'{field}' must not be empty"
        if low is not None and value < low:
            return f"'{field}' must be at least {low}"
        if high is not None and value > high:
            return f"'{field}' must be at most {high}"
    return None


def check_decision(
    decision: Optional[Dict[str, Any]], tool_calls: int
) -> Optional[Problem]:
    """Check one model reply. Returns a Problem, or None if it is acceptable."""
    if decision is None or decision.get("action") not in ("tool", "final"):
        return Problem(
            TEXT_INSTEAD,
            "your reply was not a JSON object with action 'tool' or 'final'",
        )
    if decision["action"] == "final":
        if tool_calls == 0:
            return Problem(
                TEXT_INSTEAD,
                "you answered without calling a tool; call a tool first to get facts",
            )
        if (
            not isinstance(decision.get("answer"), str)
            or not decision["answer"].strip()
        ):
            return Problem(MALFORMED, "'answer' must be a non-empty string")
        return None
    tool = decision.get("tool")
    if tool not in TOOL_SCHEMAS:
        return Problem(
            UNKNOWN_TOOL,
            f"unknown tool {tool!r}; valid tools: {sorted(TOOL_SCHEMAS)}",
        )
    message = validate_inputs(tool, decision.get("inputs", {}))
    if message:
        return Problem(MALFORMED, f"bad inputs for {tool}: {message}")
    return None


def repair_prompt(problem: Problem) -> str:
    return (
        f"Your last reply was rejected: {problem.message}. "
        "Reply again with ONLY one valid JSON object "
        '({"action": "tool", ...} or {"action": "final", ...}).'
    )


def _write_log(path: Optional[Path], record: Dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_agent(
    user_input: str,
    *,
    chat_fn: Optional[Callable[[List[Dict[str, str]]], Dict[str, Any]]] = None,
    execute: Callable[..., str] = execute_tool,
    max_iterations: int = config.MAX_ITERATIONS,
    max_failed_repairs: int = config.MAX_FAILED_REPAIRS,
    repair: bool = True,
    log_path: Optional[Path] = config.TOOL_LOG_PATH,
    run_id: str = "run",
    system_prompt: str = SYSTEM_PROMPT,
    max_tool_calls: Optional[int] = None,
    max_total_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the model/tool loop until a final answer or a hard ceiling.

    Returns the answer, stop reason, total tool calls and the per-call stats
    used for the reliability table. The optional max_tool_calls and
    max_total_tokens are hard budgets (stop reason budget_exhausted).
    """
    chat_fn = chat_fn or llm.chat
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    tool_log: List[Dict[str, Any]] = []
    failures: List[str] = []
    stats = {
        "call_attempts": 0,  # model turns that were meant to be tool calls
        "first_try_ok": 0,
        "repair_attempts": 0,
        "repair_ok": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    failed_repairs = 0
    answer: Optional[str] = None
    stop_reason = "max_iterations"
    iteration = 0

    def ask() -> Dict[str, Any]:
        reply = chat_fn(messages)
        stats["input_tokens"] += int(reply.get("input_tokens", 0))
        stats["output_tokens"] += int(reply.get("output_tokens", 0))
        return reply

    while iteration < max_iterations:
        iteration += 1
        used = stats["input_tokens"] + stats["output_tokens"]
        if max_total_tokens is not None and used >= max_total_tokens:
            stop_reason = "budget_exhausted"
            answer = "Stopped: token budget used up"
            break
        try:
            reply = ask()
        except Exception as exc:  # model unreachable: stop, do not crash
            stop_reason = "model_error"
            answer = f"Model error: {exc}"
            break
        decision = parse_decision(reply["content"])
        problem = check_decision(decision, len(tool_log))
        is_call_attempt = problem is not None or decision["action"] == "tool"
        if is_call_attempt:
            stats["call_attempts"] += 1
        if problem is None and is_call_attempt:
            stats["first_try_ok"] += 1
        if problem is not None:
            failures.append(problem.kind)
            _write_log(
                log_path,
                {
                    "run_id": run_id,
                    "iteration": iteration,
                    "event": "rejected_reply",
                    "problem": problem.kind,
                    "detail": problem.message,
                    "raw": reply["content"][:300],
                    "ts": datetime.now().isoformat(timespec="seconds"),
                },
            )
            if not repair:
                stop_reason = "rejected_no_repair"
                answer = f"Stopped: {problem.message}"
                break
            messages.append({"role": "assistant", "content": reply["content"]})
            messages.append({"role": "user", "content": repair_prompt(problem)})
            stats["repair_attempts"] += 1
            try:
                reply = ask()
            except Exception as exc:
                stop_reason = "model_error"
                answer = f"Model error: {exc}"
                break
            decision = parse_decision(reply["content"])
            problem = check_decision(decision, len(tool_log))
            if problem is not None:
                failed_repairs += 1
                messages.append({"role": "assistant", "content": reply["content"]})
                if failed_repairs >= max_failed_repairs:
                    stop_reason = "repair_failed"
                    answer = f"Stopped after failed repair: {problem.message}"
                    break
                continue
            stats["repair_ok"] += 1
        if decision["action"] == "final":
            answer = decision["answer"].strip()
            stop_reason = "final_answer"
            break
        tool, inputs = decision["tool"], decision.get("inputs", {})
        if max_tool_calls is not None and len(tool_log) >= max_tool_calls:
            stop_reason = "budget_exhausted"
            answer = "Stopped: tool-call budget used up"
            break
        result_text = execute(tool, inputs)
        try:
            result = json.loads(result_text)
        except ValueError:
            result = {"ok": False, "data": None, "error": "tool returned non-JSON"}
        entry = {
            "run_id": run_id,
            "iteration": iteration,
            "event": "tool_call",
            "tool": tool,
            "inputs": inputs,
            "ok": result.get("ok"),
            "error": result.get("error"),
            "data": result.get("data"),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        tool_log.append(entry)
        _write_log(log_path, entry)
        messages.append({"role": "assistant", "content": json.dumps(decision)})
        messages.append(
            {"role": "tool", "content": f"TOOL RESULT ({tool}): {result_text}"}
        )
    return {
        "answer": answer,
        "stop_reason": stop_reason,
        "iterations": iteration,
        "tool_calls": len(tool_log),
        "tool_log": tool_log,
        "failures": failures,
        "failed_repairs": failed_repairs,
        "total_tokens": stats["input_tokens"] + stats["output_tokens"],
        **stats,
    }
