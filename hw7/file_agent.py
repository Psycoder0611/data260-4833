"""A small tool-calling agent for the six file tools (HW7 Part 6)."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from hw7 import config, file_tools, llm
from hw7.bike_agent import parse_decision

MAX_STEPS = 8
MAX_FAILED_REPLIES = 2
OBSERVATION_CHARS = 1800

SYSTEM_PROMPT = """You are a file assistant working inside one sandbox directory.
All paths are relative to that directory.

Reply with exactly one JSON object and nothing else. Either call a tool:
{"thought": "<one short sentence>", "action": "tool", "tool": "<name>", "inputs": {...}}
or finish:
{"action": "final", "answer": "<what you found, including any file contents asked for>"}

Tools:
- glob_files {"pattern": str}: list files by name, e.g. "**/*.py".
- search_in_files {"pattern": str, "file_pattern": str}: find lines matching a
  regex inside files, e.g. {"pattern": "TODO", "file_pattern": "*.py"}.
- read_file {"path": str, "max_lines": int}: the text of one file.
- write_file {"path": str, "content": str}
- edit_file {"path": str, "old": str, "new": str}: replace text that appears once.
- bash {"command": str}: a shell command; risky ones are blocked.

A search only returns matching lines; use read_file to see a whole file.
Use only what tool results tell you. Do not repeat a call you already made."""


def _clip(text: str) -> str:
    if len(text) <= OBSERVATION_CHARS:
        return text
    return text[:OBSERVATION_CHARS] + " ...[cut]"


def run_file_agent(
    instruction: str,
    *,
    chat_fn: Callable[..., Dict[str, Any]] = llm.chat,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    temperature: float = 0.0,
    seed: int = config.SEED,
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    emit = on_event or (lambda e: None)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    calls: List[Dict[str, Any]] = []
    answer, stop, failed = None, "max_steps", 0
    started = time.perf_counter()
    steps = 0
    while steps < max_steps:
        steps += 1
        reply = chat_fn(messages, temperature=temperature, seed=seed)
        decision = parse_decision(reply["content"])
        messages.append({"role": "assistant", "content": reply["content"]})
        problem = None
        if decision is None or decision.get("action") not in ("tool", "final"):
            problem = "reply with one JSON object whose action is 'tool' or 'final'"
        elif decision["action"] == "tool":
            name = decision.get("tool")
            func = file_tools.TOOL_FUNCTIONS.get(name)
            inputs = decision.get("inputs")
            if func is None or not isinstance(inputs, dict):
                problem = f"unknown tool or bad inputs for {name!r}"
        if problem:
            failed += 1
            emit({"kind": "repair", "step": steps, "message": problem})
            if failed > MAX_FAILED_REPLIES:
                stop = "repair_failed"
                break
            messages.append({"role": "user", "content": problem})
            continue
        failed = 0
        if decision["action"] == "final":
            answer, stop = str(decision.get("answer", "")), "final_answer"
            emit({"kind": "final", "step": steps})
            break
        try:
            result = func(**inputs)
        except TypeError as exc:  # wrong argument names
            result = {"success": False, "error": f"bad inputs: {exc}"}
        calls.append(
            {"step": steps, "tool": name, "inputs": inputs,
             "success": result["success"]}
        )  # fmt: skip
        emit({"kind": "tool", "step": steps, "tool": name, "inputs": inputs,
              "success": result["success"]})  # fmt: skip
        messages.append({"role": "tool", "content": _clip(json.dumps(result))})
    return {
        "stop_reason": stop,
        "steps": steps,
        "calls": calls,
        "answer": answer,
        "total_seconds": round(time.perf_counter() - started, 2),
    }
