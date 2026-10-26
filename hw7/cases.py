"""The three fixed Part 2 verification cases (A, B, C) and their checks."""

from typing import Any, Dict, List

CASES: List[Dict[str, Any]] = [
    {
        "id": "A",
        "name": "Search, then detail-lookup the first result",
        "prompt": (
            "Search for clinical trials about 'Cardiovascular', then get the "
            "full details of the first result."
        ),
        # tool -> minimum number of calls needed for the chain to count
        "draft_prompt": (
            "Search for clinical trials about 'Cardiovascular', then get the "
            "full details of the first result."
        ),
        "required": {"search_trials": 1, "get_trial_details": 1},
        "distinct_detail_ids": 1,
        # every group must have at least one keyword in the final answer
        "answer_keywords": [["5006", "Cardiovascular Health Study"], ["120"]],
    },
    {
        "id": "B",
        "name": "Aggregate question, then one supporting example",
        "prompt": (
            "How many trials does organization 2 have, and what is their "
            "total participant capacity? Then use a search to find one "
            "example trial from that organization (search for 'Study')."
        ),
        "draft_prompt": (
            "How many trials does organization 2 have, and what is their "
            "total participant capacity? Then use a search to find one "
            "example trial from that organization."
        ),
        "required": {"organization_trial_summary": 1, "search_trials": 1},
        "distinct_detail_ids": 0,
        "answer_keywords": [["6", "six"], ["700"]],
    },
    {
        "id": "C",
        "name": "Compare two trials (search plus two detail lookups)",
        "prompt": (
            "Compare the 'Diabetes Prevention Lifestyle Study' and the "
            "'Hypertension Medication Adherence Study'. Search for them, then "
            "use get_trial_details on each one by its id, and tell me which "
            "has the larger participant capacity."
        ),
        "draft_prompt": (
            "Compare the 'Diabetes Prevention Lifestyle Study' and the "
            "'Hypertension Medication Adherence Study'. Search for them, look "
            "up the details of each, and tell me which has the larger "
            "participant capacity."
        ),
        "required": {"search_trials": 1, "get_trial_details": 2},
        "distinct_detail_ids": 2,
        "answer_keywords": [["Diabetes"], ["200"]],
    },
]


def get_case(case_id: str) -> Dict[str, Any]:
    for case in CASES:
        if case["id"] == case_id.upper():
            return case
    raise KeyError(f"Unknown case {case_id!r}")


def chain_ok(case: Dict[str, Any], tool_log: List[Dict[str, Any]]) -> bool:
    """True if every required tool was called often enough (the chain held)."""
    counts: Dict[str, int] = {}
    detail_ids = set()
    for entry in tool_log:
        counts[entry["tool"]] = counts.get(entry["tool"], 0) + 1
        if entry["tool"] == "get_trial_details":
            detail_ids.add(entry["inputs"].get("trial_id"))
    enough = all(counts.get(t, 0) >= n for t, n in case["required"].items())
    return enough and len(detail_ids) >= case["distinct_detail_ids"]


def answer_ok(case: Dict[str, Any], answer: Any) -> bool:
    """True if the final answer contains the key facts for this case."""
    if not isinstance(answer, str):
        return False
    text = answer.lower()
    return all(
        any(word.lower() in text for word in group) for group in case["answer_keywords"]
    )
