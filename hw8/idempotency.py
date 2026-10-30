"""Idempotency store: remembers which (stage, correlation_id) pairs are done.

A small SQLite file is used so the record survives a restart and is shared by
several Writer instances running on the same computer. The agents follow this
order: do the work, publish the result, mark it done, then commit the offset.
A replayed message with the same correlation_id finds the mark and is skipped.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from hw8 import config


class IdempotencyStore:
    """Persistent set of finished (stage, correlation_id) pairs."""

    def __init__(self, path: Union[str, Path, None] = None) -> None:
        """Open (and create if needed) the SQLite file."""
        target = str(path if path is not None else config.IDEMPOTENCY_DB_PATH)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            target, timeout=10, isolation_level=None, check_same_thread=False
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS done ("
            "stage TEXT NOT NULL, correlation_id TEXT NOT NULL, "
            "first_done_at REAL NOT NULL, "
            "duplicates_skipped INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (stage, correlation_id))"
        )

    def is_done(self, stage: str, correlation_id: str) -> bool:
        """True if this stage already finished this correlation_id."""
        row = self.connection.execute(
            "SELECT 1 FROM done WHERE stage = ? AND correlation_id = ?",
            (stage, correlation_id),
        ).fetchone()
        return row is not None

    def mark_done(self, stage: str, correlation_id: str) -> None:
        """Record that the stage finished (a second call changes nothing)."""
        self.connection.execute(
            "INSERT OR IGNORE INTO done (stage, correlation_id, first_done_at) "
            "VALUES (?, ?, ?)",
            (stage, correlation_id, time.time()),
        )

    def note_duplicate(self, stage: str, correlation_id: str) -> int:
        """Count one skipped duplicate and return the new total."""
        self.connection.execute(
            "UPDATE done SET duplicates_skipped = duplicates_skipped + 1 "
            "WHERE stage = ? AND correlation_id = ?",
            (stage, correlation_id),
        )
        row = self.connection.execute(
            "SELECT duplicates_skipped FROM done "
            "WHERE stage = ? AND correlation_id = ?",
            (stage, correlation_id),
        ).fetchone()
        return int(row[0]) if row else 0

    def lookup(self, stage: str, correlation_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored row as a dict, or None."""
        row = self.connection.execute(
            "SELECT first_done_at, duplicates_skipped FROM done "
            "WHERE stage = ? AND correlation_id = ?",
            (stage, correlation_id),
        ).fetchone()
        if row is None:
            return None
        return {"first_done_at": row[0], "duplicates_skipped": row[1]}

    def close(self) -> None:
        """Close the database."""
        self.connection.close()
