# ruff: noqa: E501
"""The two agents of Part 4.

AnsweringAgent  writes an answer (with lessons loaded) and revises it from feedback.
EvaluatorAgent  checks an answer against the reference dataset, returns PASS or
                REVISE with an explanation and feedback, and proposes a lesson
                when the same failure pattern repeats.

They talk through small dictionaries (the messages are logged by the runner):
  Answering -> Evaluator : {question, answer, attempt}
  Evaluator -> Answering : {result, explanation, feedback}
"""

import time
from typing import Any, Callable, Dict, List, Optional

from hw9 import config
from hw9.improve import reference as ref

LLMFunction = Callable[[List[Dict[str, str]]], str]

SYSTEM = (
    "You are the Answering Agent of a Clinical Trial Listings support assistant. "
    "Answer the question in at most three sentences of plain text. Give specific "
    "values. /no_think"
)


def stub_llm(messages: List[Dict[str, str]]) -> str:
    """Deterministic stand-in for a dry run of the code (HW9_LLM_MODE=stub).

    Never used for a reported number. It "answers" from the feedback or the lessons
    in the prompt, so the whole train / validate / final flow can be tested offline.
    """
    system, user = messages[0]["content"], messages[-1]["content"]
    if "Evaluator feedback:" in user:
        return user.split("Evaluator feedback:", 1)[1].strip().split("\n")[0]
    if "Lessons from earlier mistakes" in system:
        return system.split("Follow them:", 1)[1].strip()
    return "I am not sure."


def ollama_llm(messages: List[Dict[str, str]]) -> str:
    """Call qwen3:8b through the HW1 adapter (hw8.llm.chat, temperature 0, seed 4833)."""
    if config.LLM_MODE == "stub":
        return stub_llm(messages)
    from hw8 import llm

    return llm.chat(messages)["content"]


class AnsweringAgent:
    """Generates and revises answers."""

    def __init__(
        self,
        llm: LLMFunction = ollama_llm,
        lessons: Optional[Any] = None,
        lesson_statuses: Optional[List[str]] = None,
        lesson_ids: Optional[List[str]] = None,
        count_uses: bool = True,
    ) -> None:
        """lessons is a LessonStore or None; statuses / ids filter which lessons may load."""
        self.llm = llm
        self.lessons = lessons
        self.lesson_statuses = lesson_statuses
        self.lesson_ids = lesson_ids
        self.count_uses = count_uses

    def load_lessons(self, question: str) -> List[Dict[str, Any]]:
        """Lessons relevant to this question (and count one use for each)."""
        if self.lessons is None:
            return []
        found = self.lessons.relevant(
            question, statuses=self.lesson_statuses, ids=self.lesson_ids
        )
        if self.count_uses:
            self.lessons.mark_used(found)
        return found

    def answer(
        self,
        question: str,
        feedback: str = "",
        previous: str = "",
        loaded: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Write an answer; with feedback and the previous answer it writes a revision."""
        started = time.perf_counter()
        system = SYSTEM
        if loaded:
            system += "\n\nLessons from earlier mistakes. Follow them:\n" + "\n".join(
                f"- {lesson['correction']}" for lesson in loaded
            )
        user = f"Question: {question}"
        if feedback:
            user += (
                f"\n\nYour previous answer was:\n{previous}\n\nEvaluator feedback:\n"
                f"{feedback}\n\nWrite a corrected answer."
            )
        text = self.llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        ).strip()
        return {
            "answer": text,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "lessons_loaded": [lesson["lesson_id"] for lesson in (loaded or [])],
        }


class EvaluatorAgent:
    """Checks answers against the reference dataset."""

    def __init__(self, reference: Optional[Dict[str, Any]] = None) -> None:
        """Load reference_data.json unless a dictionary is given."""
        self.reference = reference or ref.load_reference()

    def evaluate(self, question: str, answer: str) -> ref.Verdict:
        """PASS or REVISE with explanation and feedback."""
        return ref.check_answer(self.reference, question, answer)

    def propose_lessons(
        self, failures: List[Dict[str, Any]], min_repeats: int = 2
    ) -> List[Dict[str, str]]:
        """Turn repeated failures of one topic into lesson proposals.

        failures: [{"question", "topic", "entry_id"}]. A topic that failed at least
        min_repeats times is a repeated pattern. The correction lists the reference
        facts of the entries that failed (not the whole topic).
        """
        by_topic: Dict[str, List[Dict[str, Any]]] = {}
        for failure in failures:
            if failure.get("topic"):
                by_topic.setdefault(failure["topic"], []).append(failure)
        facts = {e["id"]: e for e in self.reference["entries"]}
        proposals = []
        for topic, items in by_topic.items():
            if len(items) < min_repeats:
                continue
            info = self.reference["topics"][topic]
            ids = list(dict.fromkeys(item["entry_id"] for item in items))
            correction = info["instruction"]
            if topic != "unavailable_data":
                correction += " " + " ".join(facts[i]["fact"] for i in ids)
            proposals.append(
                {
                    "topic": topic,
                    "failure_pattern": info["failure_pattern"],
                    "correction": correction,
                    "evidence": [item["question"] for item in items],
                }
            )
        return proposals
