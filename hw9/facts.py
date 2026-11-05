# ruff: noqa: E501
"""Facts from the s4833_rel database that an answer can depend on.

A question that names a trial code (CT-2026-101 ...) is answered from the
clinical_trials row of that trial. The row's content hash is the data-version
marker stored next to the cached answer.
"""

import hashlib
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.engine import Engine

from hw9 import db

TRIAL_CODE = re.compile(r"\bCT-\d{4}-\d{3}\b", re.IGNORECASE)


def trial_codes(text: str) -> List[str]:
    """Trial codes mentioned in a text, upper-cased, in order, without repeats."""
    seen: List[str] = []
    for match in TRIAL_CODE.findall(text):
        code = match.upper()
        if code not in seen:
            seen.append(code)
    return seen


def describe_row(row: Dict) -> str:
    """One line of facts about a trial row."""
    return (
        f'Trial {row["trial_code"]}: title "{row["trialTitle"]}", sponsor '
        f'"{row["sponsor"]}", participant capacity {row["participant_capacity"]}, '
        f'category "{row.get("category") or "not set"}".'
    )


def facts_for(engine: Optional[Engine], question: str) -> Tuple[str, str, str]:
    """Return (facts_text, data_version, entity_tag) for a question.

    Questions without a trial code depend on no database record: facts_text is
    empty, the version is "static" and the entity tag is "none".
    """
    codes = trial_codes(question)
    if not codes or engine is None:
        return "", "static", "none"
    lines, versions, found = [], [], []
    for code in codes:
        row = db.get_trial_by_code(engine, code)
        if row is None:
            lines.append(f"Trial {code} does not exist in the listings database.")
            versions.append(f"{code}:missing")
        else:
            lines.append(describe_row(row))
            versions.append(f"{code}:{db.record_version(row)}")
        found.append(code)
    version = hashlib.sha1("|".join(versions).encode("utf-8")).hexdigest()[:12]
    return "\n".join(lines), version, ",".join(found)


def current_version(engine: Engine, entity_tag: str) -> str:
    """Recompute the data-version marker for a stored entity tag (for the stale check)."""
    if entity_tag in ("", "none"):
        return "static"
    codes = entity_tag.split(",")
    versions = []
    for code in codes:
        row = db.get_trial_by_code(engine, code)
        versions.append(
            f"{code}:{db.record_version(row)}" if row else f"{code}:missing"
        )
    return hashlib.sha1("|".join(versions).encode("utf-8")).hexdigest()[:12]
