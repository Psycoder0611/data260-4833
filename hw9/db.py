"""Access to the clinical_trials table in the s4833_rel MySQL database.

Plain SQL through SQLAlchemy text() is used on purpose: the HW4/HW5 models.py is
not changed. The one HW9 addition to the table is the view_count column, added by
migrate_hw09.py.
"""

import hashlib
import json
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from hw9 import config


def make_engine(url: Optional[str] = None) -> Engine:
    """Create the SQLAlchemy engine (MySQL by default, any URL in tests)."""
    return create_engine(url or config.database_url(), pool_pre_ping=True)


def get_trial_by_code(engine: Engine, trial_code: str) -> Optional[Dict[str, Any]]:
    """Return the row of one trial as a dict, or None if the code is unknown."""
    sql = text(
        "SELECT id, trial_code, trialTitle, sponsor, participant_capacity, "
        "organization_id, category FROM clinical_trials WHERE trial_code = :c"
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"c": trial_code}).mappings().first()
    return dict(row) if row else None


def get_trial_by_id(engine: Engine, trial_id: int) -> Optional[Dict[str, Any]]:
    """Return the row of one trial by primary key, or None."""
    sql = text(
        "SELECT id, trial_code, trialTitle, sponsor, participant_capacity, "
        "organization_id, category FROM clinical_trials WHERE id = :i"
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"i": trial_id}).mappings().first()
    return dict(row) if row else None


def record_version(row: Dict[str, Any]) -> str:
    """Data-version marker of a record: a short hash of its content fields.

    It changes whenever the title, sponsor, capacity, organisation or category
    changes, so a cached answer built from the old row can be recognised as stale.
    """
    fields = {
        k: row.get(k)
        for k in (
            "trial_code",
            "trialTitle",
            "sponsor",
            "participant_capacity",
            "organization_id",
            "category",
        )
    }
    blob = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def update_capacity(engine: Engine, trial_code: str, capacity: int) -> int:
    """Set participant_capacity of one trial; returns the number of rows changed."""
    sql = text(
        "UPDATE clinical_trials SET participant_capacity = :cap WHERE trial_code = :c"
    )
    with engine.begin() as conn:
        return conn.execute(sql, {"cap": capacity, "c": trial_code}).rowcount


def get_view_count(engine: Engine, trial_id: int) -> Optional[int]:
    """Return the persisted view_count of one trial."""
    sql = text(f"SELECT {config.VIEWS_COLUMN} FROM {config.TRIALS_TABLE} WHERE id = :i")
    with engine.connect() as conn:
        value = conn.execute(sql, {"i": trial_id}).scalar()
    return None if value is None else int(value)


def set_view_count(engine: Engine, trial_id: int, count: int) -> int:
    """Persist the view count of one trial; returns rows changed."""
    sql = text(
        f"UPDATE {config.TRIALS_TABLE} SET {config.VIEWS_COLUMN} = :n WHERE id = :i"
    )
    with engine.begin() as conn:
        return conn.execute(sql, {"n": count, "i": trial_id}).rowcount
