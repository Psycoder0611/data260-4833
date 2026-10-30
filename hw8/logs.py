"""Console logging, the student banner and the RUN_LOG tee for HW8 scripts.

Every log line looks like ``HH:MM:SS.mmm [COMPONENT] message`` so the send,
receive, process, reply and client-response lines can be read in order.
"""

import contextlib
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, TextIO

from hw8 import config


class _LiveStdoutHandler(logging.Handler):
    """Write to whatever sys.stdout is at emit time (so a tee still sees it)."""

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record and write it to the current sys.stdout."""
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:  # logging must never crash the program
            self.handleError(record)


class _Formatter(logging.Formatter):
    """Format as ``HH:MM:SS.mmm [NAME] message`` in local time."""

    def format(self, record: logging.LogRecord) -> str:
        """Return one console line for this record."""
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        return f"{stamp} [{record.name}] {record.getMessage()}"


def get_logger(component: str) -> logging.Logger:
    """Return a logger whose lines are tagged with the component name."""
    logger = logging.getLogger(component.upper())
    if not logger.handlers:
        handler = _LiveStdoutHandler()
        handler.setFormatter(_Formatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def banner(title: str) -> str:
    """Return the identification line used at the top of every run."""
    return (
        f"Student: {config.STUDENT_NAME} | SID4 {config.SID4} | "
        f"HW{config.HOMEWORK} {title}"
    )


def to_json(value: Any) -> str:
    """Compact JSON for log lines (keys in insertion order, no spaces)."""
    return json.dumps(value, separators=(",", ":"), default=str)


class _Tee:
    """File-like object that writes to two streams."""

    def __init__(self, first: TextIO, second: TextIO) -> None:
        """Remember both streams."""
        self.first = first
        self.second = second

    def write(self, text: str) -> int:
        """Write to both streams."""
        self.first.write(text)
        self.second.write(text)
        return len(text)

    def flush(self) -> None:
        """Flush both streams."""
        self.first.flush()
        self.second.flush()

    def isatty(self) -> bool:
        """Report that this is not a terminal."""
        return False


@contextlib.contextmanager
def run_logged(title: str, path: Optional[Path] = None) -> Iterator[None]:
    """Copy everything printed inside the block to RUN_LOG.txt (append mode).

    The block is wrapped in START and END marker lines with the date, the same
    way as the HW6/HW7 run logs, and the student banner is printed first.
    """
    log_path = path or config.RUN_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    original = sys.stdout
    with open(log_path, "a", encoding="utf-8") as handle:
        stamp = time.strftime("%a %b %d %H:%M:%S %Z %Y")
        handle.write(f"===== HW8 {title.upper()} RUN START: {stamp} =====\n")
        sys.stdout = _Tee(original, handle)  # type: ignore[assignment]
        try:
            print(banner(title))
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            yield
        finally:
            sys.stdout = original
            stamp = time.strftime("%a %b %d %H:%M:%S %Z %Y")
            handle.write(f"===== HW8 {title.upper()} RUN END: {stamp} =====\n")


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """Append one JSON object as a line to a .jsonl file (creating folders)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def read_jsonl(path: Path) -> list:
    """Read a .jsonl file into a list of dicts (missing file -> empty list)."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
