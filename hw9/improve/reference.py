# ruff: noqa: E501
"""The reference dataset and the comparison of an answer against it.

reference_data.json is the ground truth. match_entry() finds the fact that a
question is about (by keyword groups); check_answer() compares an answer with it.
Nothing here calls a model, so the comparison is repeatable.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from hw9 import config

REFERENCE_PATH = config.DATA_DIR / "reference_data.json"


@dataclass
class Verdict:
    """Result of comparing one answer with the reference."""

    result: str  # "PASS" or "REVISE"
    explanation: str
    feedback: str = ""
    entry_id: Optional[str] = None
    topic: Optional[str] = None
    kind: str = "out_of_domain"
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True when the answer agrees with the reference."""
        return self.result == "PASS"


def load_reference(path: Path = REFERENCE_PATH) -> Dict[str, Any]:
    """Read reference_data.json."""
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Lower-case, join 2,000 -> 2000 and collapse spaces."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def contains(text: str, alt: str) -> bool:
    """True if alt occurs in text; a purely numeric alt must stand alone (no 2000 in 20000)."""
    alt = alt.lower()
    if re.fullmatch(r"[\d.]+", alt):
        pattern = r"(?<![\w.,-])" + re.escape(alt) + r"(?![\w-]|[.,]\d)"
        return re.search(pattern, text) is not None
    return alt in text


def match_entry(reference: Dict[str, Any], question: str) -> Optional[Dict[str, Any]]:
    """The reference entry a question is about, or None for unrelated questions.

    An entry matches when all keywords of one of its trigger groups occur in the
    question; the entry with the largest matching group wins (ties: first listed).
    """
    q = question.lower()
    best, best_size = None, 0
    for entry in reference["entries"]:
        for group in entry["triggers"]:
            if all(word in q for word in group) and len(group) > best_size:
                best, best_size = entry, len(group)
    return best


def check_answer(reference: Dict[str, Any], question: str, answer: str) -> Verdict:
    """Compare an answer with the reference facts for its question."""
    text = normalize(answer)
    entry = match_entry(reference, question)
    if entry is None:
        leaked = [m for m in reference["domain_markers"] if contains(text, m)]
        if leaked:
            return Verdict(
                "REVISE",
                f"The question is unrelated to the listings, but the answer mentions {leaked}.",
                "Answer only what was asked. The question has nothing to do with "
                "clinical trial listings, so do not mention listing rules or values.",
                kind="out_of_domain",
                details={"leaked": leaked},
            )
        return Verdict(
            "PASS",
            "Unrelated question; the answer adds no listing facts.",
            kind="out_of_domain",
        )
    if entry["kind"] == "no_data":
        said = [m for m in reference["refusal_markers"] if m in text]
        if said:
            return Verdict(
                "PASS",
                "The answer says the value is not available, as the reference requires.",
                entry_id=entry["id"],
                topic=entry["topic"],
                kind="no_data",
            )
        return Verdict(
            "REVISE",
            "The listings data has no such value, but the answer gives one.",
            f"Reference ({entry['id']}): {entry['fact']} Do not guess. Say that the "
            "information is not available.",
            entry_id=entry["id"],
            topic=entry["topic"],
            kind="no_data",
        )
    missing = [
        g for g in entry["must_include"] if not any(contains(text, a) for a in g)
    ]
    if not missing:
        return Verdict(
            "PASS",
            "The answer contains the value from the reference.",
            entry_id=entry["id"],
            topic=entry["topic"],
            kind="fact",
        )
    return Verdict(
        "REVISE",
        f"The answer does not contain the reference value {missing[0]}.",
        f"Reference ({entry['id']}): {entry['fact']} State this value exactly.",
        entry_id=entry["id"],
        topic=entry["topic"],
        kind="fact",
        details={"missing": missing},
    )
