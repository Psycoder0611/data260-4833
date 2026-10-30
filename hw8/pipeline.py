"""Planner, Writer and Reviewer logic for the Part 2 Kafka pipeline.

Each handler takes one message dict and returns the next message dict. Handlers
know nothing about Kafka; hw8/agent_base.py moves the messages. The language
model is behind a Brain object so tests and the failure demos can use a
deterministic stub instead of qwen3:8b.

Message flow (correlation_id is copied unchanged at every step):
  s4833_inbox   {correlation_id, question}
  s4833_tasks   {correlation_id, question, plan: [steps]}
  s4833_drafts  {correlation_id, question, plan, draft}
  s4833_final   {correlation_id, status, answer, score, feedback}
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from hw8 import config
from hw8.logs import append_jsonl

Handler = Callable[
    [Dict[str, Any], Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]
]

# fields that travel with a message through every stage (used by the failure tests)
CARRY_FIELDS = ("entity", "seq", "work_ms", "test_run")
MAX_DRAFT_WORDS = 220


def now_iso() -> str:
    """Current UTC time, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_json(text: str) -> Dict[str, Any]:
    """Find the first JSON object in a model reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("model reply has no JSON object")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"model reply JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("model reply JSON is not an object")
    return value


def carry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Copy the pass-through fields from one stage's message to the next."""
    return {k: payload[k] for k in CARRY_FIELDS if k in payload}


def require_text(payload: Dict[str, Any], field: str) -> str:
    """Return a non-empty string field or raise ValueError."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


class Brain:
    """Produces the text for each role: real model (ollama) or deterministic stub."""

    def __init__(self, mode: str = "ollama", work_seconds: float = 0.0) -> None:
        """Choose the mode; work_seconds adds a fixed delay in stub mode."""
        if mode not in ("ollama", "stub"):
            raise ValueError("mode must be 'ollama' or 'stub'")
        self.mode = mode
        self.work_seconds = work_seconds

    # ---- helpers
    def _ask(self, system: str, user: str) -> str:
        """Call the local model and return the cleaned reply text."""
        from hw8 import llm

        reply = llm.chat(
            [
                {"role": "system", "content": system + " /no_think"},
                {"role": "user", "content": user},
            ]
        )
        return reply["content"]

    def _stub_wait(self, payload: Dict[str, Any]) -> None:
        """Sleep for the message's own work time (work_ms) or the default."""
        if "work_ms" in payload:
            seconds = float(payload["work_ms"]) / 1000
        else:
            seconds = self.work_seconds
        if seconds > 0:
            time.sleep(seconds)

    # ---- roles (blocking calls; the agents run them in a worker thread)
    def plan(self, payload: Dict[str, Any]) -> List[str]:
        """Return 3 short plan steps for the question."""
        question = require_text(payload, "question")
        if self.mode == "stub":
            self._stub_wait(payload)
            return [
                f"Identify what the question asks: {question[:60]}",
                "Collect the relevant clinical trial listing rules",
                "Summarise the answer in plain language",
            ]
        text = self._ask(
            "You are the Planner agent of a clinical trial listings assistant. "
            'Reply with ONLY JSON like {"steps": ["...", "...", "..."]}: exactly '
            "3 short steps (at most 12 words each) for answering the question.",
            question,
        )
        steps = extract_json(text).get("steps")
        if (
            not isinstance(steps, list)
            or len(steps) != 3
            or not all(isinstance(s, str) and s.strip() for s in steps)
        ):
            raise ValueError("planner must return exactly 3 non-empty steps")
        return [s.strip() for s in steps]

    def write(self, payload: Dict[str, Any], plan: List[str]) -> str:
        """Return a draft answer that follows the plan."""
        question = require_text(payload, "question")
        if self.mode == "stub":
            self._stub_wait(payload)
            return f"Draft answer to '{question[:60]}' following {len(plan)} steps."
        text = self._ask(
            "You are the Writer agent of a clinical trial listings assistant. "
            "Write a clear draft answer of at most 120 words, in plain text, "
            "that follows the plan. Do not use markdown headings.",
            f"Question: {question}\nPlan:\n" + "\n".join(f"- {s}" for s in plan),
        )
        if not text.strip():
            raise ValueError("writer produced an empty draft")
        return text.strip()

    def review(self, payload: Dict[str, Any], draft: str) -> Dict[str, Any]:
        """Return {"score": 1-10, "feedback": str} for the draft."""
        if self.mode == "stub":
            self._stub_wait(payload)
            return {"score": 8, "feedback": "Stub review: draft is acceptable."}
        text = self._ask(
            "You are the Reviewer agent of a clinical trial listings assistant. "
            "Check the draft for accuracy, clarity and whether it answers the "
            'question. Reply with ONLY JSON like {"score": 7, "feedback": "one '
            'sentence"} where score is an integer from 1 to 10.',
            f"Question: {payload.get('question', '')}\nDraft:\n{draft}",
        )
        data = extract_json(text)
        score = data.get("score")
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not 1 <= score <= 10
        ):
            raise ValueError("reviewer score must be an integer from 1 to 10")
        feedback = data.get("feedback")
        if not isinstance(feedback, str) or not feedback.strip():
            raise ValueError("reviewer feedback must be a non-empty string")
        return {"score": score, "feedback": feedback.strip()}


def make_planner(brain: Brain) -> Handler:
    """Build the Planner handler: inbox question -> tasks plan."""

    async def planner(
        payload: Dict[str, Any], ctx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Turn a question into a 3-step plan."""
        steps = await asyncio.to_thread(brain.plan, payload)
        return {
            "correlation_id": payload["correlation_id"],
            "stage": "plan",
            "question": require_text(payload, "question"),
            "plan": steps,
            "planned_by": ctx.get("agent", "planner"),
            "created_at": now_iso(),
            **carry(payload),
        }

    return planner


def make_writer(brain: Brain, record_path: Optional[Path] = None) -> Handler:
    """Build the Writer handler: tasks plan -> drafts draft.

    If record_path is given, one line per finished message is appended (instance,
    partition, offset, entity, seq, start and finish time). The ordering test
    reads this file to see in what order the messages were processed.
    """

    async def writer(
        payload: Dict[str, Any], ctx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Write a draft for the plan; a malformed plan is a poison message."""
        plan = payload.get("plan")
        if (
            not isinstance(plan, list)
            or not plan
            or not all(isinstance(s, str) and s.strip() for s in plan)
        ):
            raise ValueError("plan must be a non-empty list of non-empty strings")
        started = time.time()
        draft = await asyncio.to_thread(brain.write, payload, plan)
        finished = time.time()
        if record_path is not None:
            append_jsonl(
                record_path,
                {
                    "instance": ctx.get("instance"),
                    "partition": ctx.get("partition"),
                    "offset": ctx.get("offset"),
                    "correlation_id": payload["correlation_id"],
                    "entity": payload.get("entity"),
                    "seq": payload.get("seq"),
                    "started": started,
                    "finished": finished,
                },
            )
        return {
            "correlation_id": payload["correlation_id"],
            "stage": "draft",
            "question": payload.get("question"),
            "plan": plan,
            "draft": draft,
            "written_by": ctx.get("agent", "writer"),
            "created_at": now_iso(),
            **carry(payload),
        }

    return writer


def make_reviewer(brain: Brain) -> Handler:
    """Build the Reviewer handler: drafts draft -> final approval."""

    async def reviewer(
        payload: Dict[str, Any], ctx: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Approve or reject a draft; messages made by the failure tests are skipped."""
        if payload.get("test_run"):
            return None  # failure-test traffic is not reviewed
        draft = require_text(payload, "draft")
        problems = []
        if len(draft.split()) > MAX_DRAFT_WORDS:
            problems.append(f"draft is longer than {MAX_DRAFT_WORDS} words")
        verdict = await asyncio.to_thread(brain.review, payload, draft)
        approved = verdict["score"] >= config.APPROVAL_MIN_SCORE and not problems
        return {
            "correlation_id": payload["correlation_id"],
            "stage": "final",
            "status": "approved" if approved else "rejected",
            "answer": draft,
            "score": verdict["score"],
            "feedback": " ".join([verdict["feedback"], *problems]),
            "question": payload.get("question"),
            "reviewed_by": ctx.get("agent", "reviewer"),
            "created_at": now_iso(),
        }

    return reviewer
