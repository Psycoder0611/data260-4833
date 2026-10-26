"""HW7 Part 3: deterministic verifiers, one per fixed task.

Each verifier looks only at the tool log (what the tools really returned) and
the final answer. No model is involved, so the same run always gets the same
verdict.
"""

import json
import re
from typing import Any, Dict, List

TARGET_TITLES = (
    "Diabetes Prevention Lifestyle Study",
    "Hypertension Medication Adherence Study",
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers(text: str) -> set:
    """Numbers in a text, with thousands separators removed (1,200 -> 1200)."""
    return set(_NUMBER.findall(re.sub(r"(?<=\d),(?=\d)", "", text or "")))


def unsupported_claims(prompt: str, answer: Any, tool_log: List[dict]) -> List[str]:
    """Numbers in the answer that are in neither the question nor a tool result."""
    if not isinstance(answer, str):
        return []
    seen = _numbers(prompt)
    for entry in tool_log:
        seen |= _numbers(json.dumps(entry.get("data"), default=str))
        seen |= _numbers(json.dumps(entry.get("inputs"), default=str))
    return sorted(_numbers(answer) - seen)


def _ok_calls(tool_log: List[dict], tool: str) -> List[dict]:
    return [e for e in tool_log if e["tool"] == tool and e.get("ok")]


def _search_trials(tool_log: List[dict]) -> List[dict]:
    found: List[dict] = []
    for entry in _ok_calls(tool_log, "search_trials"):
        found.extend(entry.get("data") or [])
    return found


def _detail_for(tool_log: List[dict], trial_id: Any) -> Dict[str, Any]:
    for entry in _ok_calls(tool_log, "get_trial_details"):
        if (entry.get("data") or {}).get("id") == trial_id:
            return entry["data"]
    return {}


def _mentions(answer: str, trial: Dict[str, Any]) -> bool:
    text = (answer or "").lower()
    title = str(trial.get("trialTitle", "")).lower()
    code = str(trial.get("trial_code", "")).lower()
    return bool((title and title in text) or (code and code in text))


def _check(name: str, passed: bool, evidence: str, hint: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence, "hint": hint}


def _verify_a(log: List[dict], answer: str) -> List[Dict[str, Any]]:
    results = _search_trials(log)
    first = results[0] if results else {}
    asked = [
        e["inputs"].get("trial_id") for e in log if e["tool"] == "get_trial_details"
    ]
    # Use the details if they were fetched, otherwise the search row.
    record = _detail_for(log, first.get("id")) or first
    stated = bool(record) and _mentions(answer, record)
    stated = stated and str(record.get("participant_capacity")) in _numbers(answer)
    return [
        _check(
            "search returned at least one trial",
            bool(results),
            f"search results: {len(results)}",
            "call search_trials with a word from the title first",
        ),
        _check(
            "details looked up for the first search result",
            bool(first) and first.get("id") in asked,
            f"first result id {first.get('id')}, detail ids requested {asked}",
            "call get_trial_details with the id of the first search result",
        ),
        _check(
            "answer gives the first result's title and capacity",
            stated,
            f"answer: {(answer or '')[:120]!r}",
            "state the title and participant capacity of the first result",
        ),
    ]


def _verify_b(log: List[dict], answer: str) -> List[Dict[str, Any]]:
    summaries = [
        e
        for e in _ok_calls(log, "organization_trial_summary")
        if e["inputs"].get("organization_id") == 2
    ]
    summary = summaries[0]["data"] if summaries else {}
    numbers = _numbers(answer)
    results = _search_trials(log)
    return [
        _check(
            "organization summary fetched for organization 2",
            bool(summary),
            f"summary calls ok: {len(summaries)}",
            "call organization_trial_summary with organization_id 2",
        ),
        _check(
            "answer has the trial count and total capacity",
            bool(summary)
            and str(summary.get("trial_count")) in numbers
            and str(summary.get("total_participant_capacity")) in numbers,
            f"summary: count {summary.get('trial_count')}, "
            f"total {summary.get('total_participant_capacity')}",
            "report the trial count and total capacity from the summary",
        ),
        _check(
            "one example trial found by search and named",
            bool(results) and any(_mentions(answer, t) for t in results),
            f"search results: {len(results)}",
            "search a word that appears in titles, such as Study, and name one result",
        ),
    ]


def _verify_c(log: List[dict], answer: str) -> List[Dict[str, Any]]:
    by_title = {t["trialTitle"]: t for t in _search_trials(log)}
    rows = [by_title[t] for t in TARGET_TITLES if t in by_title]
    ids = [r["id"] for r in rows]
    asked = [
        e["inputs"].get("trial_id") for e in log if e["tool"] == "get_trial_details"
    ]
    # Use the details if they were fetched, otherwise the search row.
    records = [_detail_for(log, r["id"]) or r for r in rows]
    numbers = _numbers(answer)
    states = False
    if len(records) == 2:
        larger = max(records, key=lambda d: d.get("participant_capacity") or 0)
        states = _mentions(answer, larger) and all(
            str(d.get("participant_capacity")) in numbers for d in records
        )
    return [
        _check(
            "both trials found in search results",
            len(ids) == 2,
            f"ids found: {ids}",
            "search for each trial title and note its id",
        ),
        _check(
            "details looked up for both trials",
            len(ids) == 2 and all(i in asked for i in ids),
            f"ids found {ids}, detail ids requested {asked}",
            "call get_trial_details once for each of the two ids",
        ),
        _check(
            "answer names the larger trial with both capacities",
            states,
            f"answer: {(answer or '')[:120]!r}",
            "compare the two capacities and name the larger trial",
        ),
    ]


_VERIFIERS = {"A": _verify_a, "B": _verify_b, "C": _verify_c}


def verify(
    case_id: str, prompt: str, tool_log: List[dict], answer: Any, stop_reason: str
) -> Dict[str, Any]:
    """Return the verdict: passed, every assertion with evidence, unsupported claims."""
    finished = stop_reason == "final_answer"
    checks = [
        _check(
            "run ended with a final answer",
            finished,
            f"stop reason: {stop_reason}",
            "finish with a final answer after the tool calls",
        )
    ]
    text = answer if isinstance(answer, str) else ""
    checks += _VERIFIERS[case_id](tool_log, text)
    extra = unsupported_claims(prompt, answer, tool_log)
    checks.append(
        _check(
            "every number in the answer comes from a tool result",
            not extra,
            f"unsupported numbers: {extra}",
            "only state numbers that appear in the tool results",
        )
    )
    return {
        "passed": all(c["passed"] for c in checks),
        "assertions": checks,
        "unsupported_claims": extra,
    }
