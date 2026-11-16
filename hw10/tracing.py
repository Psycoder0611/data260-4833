# ruff: noqa: E501
"""Structured spans: one JSON line per pipeline stage, keyed by trace_id.

trace_id IS the HW8 correlation_id (no second ID). Every stage appends one span

    {"trace_id", "stage", "start", "end", "status", "error", ...}

to a JSON-lines file (reports/hw10/raw/spans.jsonl). start and end are UTC ISO-8601
timestamps with milliseconds; status is "ok" or "error"; error is null or text.
Extra fields: duration_ms, component (which process wrote it) and attrs (a small
dict with stage details such as cache similarity or reviewer score).

Several processes (ingress, planner, writer, reviewer, evaluator) append to the same
file. One span is one write() call on a file opened in append mode, so lines do not
interleave for small spans.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from hw10 import config

# Stage names, in the order a cache-miss request passes through them.
CACHE_LOOKUP = "cache_lookup"
QUEUE_INBOX = "queue_inbox"  # waiting in s4833_inbox for the Planner
PLANNER = "planner"
QUEUE_TASKS = "queue_tasks"  # waiting in s4833_tasks for the Writer
WRITER = "writer"
QUEUE_DRAFTS = "queue_drafts"  # waiting in s4833_drafts for the Reviewer
REVIEWER = "reviewer"
QUEUE_FINAL = "queue_final"  # waiting in s4833_final for the ingress
DEAD_LETTER = "dead_letter"
REQUEST = "request"  # the whole request as the caller sees it
EVALUATION = "evaluation"  # the evaluator, after the answer was returned

QUEUE_STAGES = (QUEUE_INBOX, QUEUE_TASKS, QUEUE_DRAFTS, QUEUE_FINAL)
STAGE_ORDER = (
    CACHE_LOOKUP,
    QUEUE_INBOX,
    PLANNER,
    QUEUE_TASKS,
    WRITER,
    QUEUE_DRAFTS,
    REVIEWER,
    QUEUE_FINAL,
    DEAD_LETTER,
    REQUEST,
    EVALUATION,
)
TOPIC_TO_QUEUE = {
    config.INBOX_TOPIC: QUEUE_INBOX,
    config.TASKS_TOPIC: QUEUE_TASKS,
    config.DRAFTS_TOPIC: QUEUE_DRAFTS,
    config.FINAL_TOPIC: QUEUE_FINAL,
}


def iso(timestamp: float) -> str:
    """UTC ISO-8601 with milliseconds, e.g. 2026-11-16T18:30:01.123+00:00."""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(
        timespec="milliseconds"
    )


def parse_iso(text: str) -> float:
    """Inverse of iso(): epoch seconds."""
    return datetime.fromisoformat(text).timestamp()


def make_span(
    trace_id: str,
    stage: str,
    start: float,
    end: float,
    status: str = "ok",
    error: Optional[str] = None,
    component: str = "",
    attrs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one span dict (start and end are epoch seconds)."""
    return {
        "trace_id": trace_id,
        "stage": stage,
        "start": iso(start),
        "end": iso(end),
        "status": status,
        "error": error,
        "duration_ms": round((end - start) * 1000, 1),
        "component": component,
        "attrs": attrs or {},
    }


def emit(span: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Append one span to the span file (creating folders)."""
    target = Path(path) if path else config.SPANS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(span, default=str) + "\n"
    fd = os.open(str(target), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))  # one write call -> one whole line
    finally:
        os.close(fd)


def record(
    trace_id: str,
    stage: str,
    start: float,
    end: float,
    status: str = "ok",
    error: Optional[str] = None,
    component: str = "",
    attrs: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """make_span() + emit() in one call; returns the span."""
    span = make_span(trace_id, stage, start, end, status, error, component, attrs)
    emit(span, path)
    return span


class Span:
    """Context manager: times a block and writes the span when it ends.

    An exception inside the block is recorded as status "error" with the error
    text, and then re-raised. Use .attrs to add details before the block ends.
    """

    def __init__(
        self,
        trace_id: str,
        stage: str,
        component: str = "",
        path: Optional[Path] = None,
        **attrs: Any,
    ) -> None:
        """Remember what to write; the clock starts in __enter__."""
        self.trace_id = trace_id
        self.stage = stage
        self.component = component
        self.path = path
        self.attrs: Dict[str, Any] = dict(attrs)
        self.start = 0.0
        self.status = "ok"
        self.error: Optional[str] = None
        self.span: Optional[Dict[str, Any]] = None

    def __enter__(self) -> "Span":
        """Start the clock."""
        self.start = time.time()
        return self

    def fail(self, error: str) -> None:
        """Mark the span as failed without raising."""
        self.status = "error"
        self.error = error

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Write the span; never swallow the exception."""
        if exc is not None:
            self.status = "error"
            self.error = f"{type(exc).__name__}: {exc}"
        self.span = record(
            self.trace_id,
            self.stage,
            self.start,
            time.time(),
            self.status,
            self.error,
            self.component,
            self.attrs,
            self.path,
        )
        return False


def read_spans(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every span; unreadable lines are skipped (a crash can cut a line)."""
    target = Path(path) if path else config.SPANS_PATH
    if not target.exists():
        return []
    spans = []
    with open(target, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("trace_id"):
                spans.append(value)
    return spans


def group_by_trace(spans: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """{trace_id: spans sorted by start time (ties broken by stage order)}."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for span in spans:
        out.setdefault(span["trace_id"], []).append(span)
    rank = {name: i for i, name in enumerate(STAGE_ORDER)}
    for items in out.values():
        items.sort(key=lambda s: (s["start"], rank.get(s["stage"], 99)))
    return out


def trace_path(spans: List[Dict[str, Any]]) -> str:
    """"hit", "miss" or "unknown" from the cache_lookup span of one trace."""
    for span in spans:
        if span["stage"] == CACHE_LOOKUP:
            hit = (span.get("attrs") or {}).get("cache_hit")
            return "hit" if hit else "miss"
    return "unknown"


def trace_status(spans: List[Dict[str, Any]]) -> str:
    """"ok" or "error" for the whole request (from the request span)."""
    for span in spans:
        if span["stage"] == REQUEST:
            return span["status"]
    return "error" if any(s["status"] == "error" for s in spans) else "ok"


def failing_stage(spans: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first span with status "error" that is not the request/dead_letter wrapper."""
    for span in spans:
        if span["status"] == "error" and span["stage"] not in (REQUEST, DEAD_LETTER):
            return span
    for span in spans:
        if span["status"] == "error":
            return span
    return None
