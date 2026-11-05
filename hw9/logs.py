# ruff: noqa: E501
"""Logging helpers for HW9: timestamped lines and the student banner."""

import logging
import sys
from datetime import datetime

from hw9 import config


class _LiveStdoutHandler(logging.Handler):
    """Write to whatever sys.stdout is at emit time."""

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record and write it to the current sys.stdout."""
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
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
    """Identification line printed at the top of every run (name visible in screenshots)."""
    return (
        f"Student: {config.STUDENT_NAME} | SID4 {config.SID4} | "
        f"HW{config.HOMEWORK} {title}"
    )
