"""The HW8 agent path used on a cache miss.

Planner, Writer and Reviewer are the same Brain roles as in the Kafka pipeline of
HW8 (hw8/pipeline.py, local qwen3:8b through the HW1 adapter). Here they are called
one after another in this process, so a cache measurement does not need Kafka and
three agent processes running. Each role keeps the HW8 retry rule (up to
MAX_ATTEMPTS tries) and the HW8 approval rule (review score >= 6).
"""

import time
from typing import Any, Dict, Optional

from hw8 import config as hw8_config
from hw8.pipeline import Brain
from hw9 import config


class HW8Agents:
    """question -> {answer, score, status, agent_ms}."""

    def __init__(self, brain: Optional[Brain] = None) -> None:
        """Use the given Brain, or build one from HW9_LLM_MODE (ollama or stub)."""
        self.brain = brain or Brain(mode=config.LLM_MODE)

    def _retry(self, fn, *args):
        """Call one role; retry like the HW8 agents do (3 attempts)."""
        last: Optional[Exception] = None
        for attempt in range(1, hw8_config.MAX_ATTEMPTS + 1):
            try:
                return fn(*args)
            except (
                ValueError
            ) as exc:  # bad model output (HW8 treats it as a failed attempt)
                last = exc
                time.sleep(hw8_config.RETRY_BACKOFF_SECONDS * attempt)
        raise RuntimeError(f"agent role failed after retries: {last}")

    def run(self, question: str, facts: str = "") -> Dict[str, Any]:
        """Run Planner, Writer and Reviewer for one question."""
        started = time.perf_counter()
        text = question
        if facts:
            text = (
                f"{question}\n\nFacts from the listings database (use them exactly):\n"
                f"{facts}"
            )
        payload = {"question": text}
        plan = self._retry(self.brain.plan, payload)
        draft = self._retry(self.brain.write, payload, plan)
        review = self._retry(self.brain.review, payload, draft)
        score = int(review["score"])
        return {
            "answer": draft,
            "score": score,
            "status": "approved"
            if score >= hw8_config.APPROVAL_MIN_SCORE
            else "rejected",
            "agent_ms": round((time.perf_counter() - started) * 1000, 1),
        }
