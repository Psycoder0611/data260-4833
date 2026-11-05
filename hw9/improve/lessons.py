# ruff: noqa: E501
"""lessons.json: reusable lessons created from repeated failure patterns.

Each lesson has lesson_id, failure_pattern, correction, created_at and use_count,
plus three bookkeeping fields: topic, status (candidate / kept / rejected) and
source. A lesson is loaded for a question when they share at least one content
word, so an unrelated question loads nothing.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from hw9 import config

LESSONS_PATH = config.DATA_DIR / "lessons.json"
STOP = set(
    "the a an of to is are what which how who when where can be do does for in on at "
    "and or it its this that with by from as into after before than then there their "
    "trial trials listing listings answer value values data number field fields say "
    "use these exact exactly clearly instead every detail asked not may much many "
    "platform fixed".split()
)


def content_words(text: str) -> set:
    """Lower-case words without stop words and very short words."""
    return {
        w
        for w in re.findall(r"[a-z0-9_\-]+", text.lower())
        if w not in STOP and len(w) > 2
    }


class LessonStore:
    """Reads and writes lessons.json."""

    def __init__(self, path: Path = LESSONS_PATH) -> None:
        """Load the file if it exists."""
        self.path = path
        self.lessons: List[Dict[str, Any]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        )

    def save(self) -> None:
        """Write lessons.json."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.lessons, indent=2), encoding="utf-8")

    def next_id(self) -> str:
        """lesson_001, lesson_002, ..."""
        return f"lesson_{len(self.lessons) + 1:03d}"

    def add(
        self,
        failure_pattern: str,
        correction: str,
        topic: str,
        source: str = "training_failures",
    ) -> Dict[str, Any]:
        """Create and save a new candidate lesson."""
        lesson = {
            "lesson_id": self.next_id(),
            "failure_pattern": failure_pattern,
            "correction": correction,
            "created_at": date.today().isoformat(),
            "use_count": 0,
            "topic": topic,
            "status": "candidate",
            "source": source,
        }
        self.lessons.append(lesson)
        self.save()
        return lesson

    def relevant(
        self,
        question: str,
        statuses: Optional[List[str]] = None,
        ids: Optional[List[str]] = None,
        limit: int = 3,
        min_overlap: int = 1,
    ) -> List[Dict[str, Any]]:
        """Lessons that share enough words with the question, best first."""
        words = content_words(question)
        scored = []
        for lesson in self.lessons:
            if statuses is not None and lesson["status"] not in statuses:
                continue
            if ids is not None and lesson["lesson_id"] not in ids:
                continue
            overlap = len(
                words
                & content_words(lesson["failure_pattern"] + " " + lesson["correction"])
            )
            if overlap >= min_overlap:
                scored.append((overlap, lesson))
        scored.sort(key=lambda pair: -pair[0])
        return [lesson for _, lesson in scored[:limit]]

    def mark_used(self, lessons: List[Dict[str, Any]]) -> None:
        """Count one use for each loaded lesson and save."""
        for lesson in lessons:
            lesson["use_count"] += 1
        if lessons:
            self.save()
