"""Run one Bay Wheels scenario and save the evidence (HW7 Part 4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from hw7 import bike_agent, bike_costs, bike_policy, llm
from hw7.bike_policy import file_sha256
from hw7.bike_tools import BikeTools
from hw7.config import RAW_DIR

TOLERANCE = 0.011  # the SQL rounds each week to cents


def _first_rows(log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for e in log:
        if e.get("kind") == "tool" and e["tool"] == "csv_sql" and e["success"]:
            rows = e["full_observation"]["data"]["rows"]
            if rows and "week" in rows[0] and "rides" in rows[0]:
                return rows
    return []


def _snippets(log: List[Dict[str, Any]]) -> List[str]:
    for e in log:
        if e.get("kind") == "tool" and e["tool"] == "policy_retriever" and e["success"]:
            return [p["text"] for p in e["full_observation"]["data"]["passages"]]
    return []


def _membership_fee(snippets: List[str]) -> Optional[float]:
    for text in snippets:
        m = re.match(r"Month pass: \$([\d.]+)", text)
        if m:
            return float(m.group(1))
    return None


def _close(a: Any, b: Any, tol: float = TOLERANCE) -> bool:
    return isinstance(a, (int, float)) and abs(float(a) - float(b)) <= tol


def summarize(
    run: Dict[str, Any], tools: BikeTools, csv_path: str, rider_id: str
) -> Dict[str, Any]:
    final = run["final"]
    log = run["log"]
    calcs = bike_agent.calc_values(log)
    snippets = _snippets(log)
    weekly = _first_rows(log)
    ref = bike_costs.reference(csv_path, rider_id)
    result: Dict[str, Any] = {
        "rider_id": rider_id,
        "stop_reason": run["stop_reason"],
        "steps": run["steps"],
        "total_seconds": run["total_seconds"],
        "tool_calls": sum(1 for e in log if e.get("kind") == "tool"),
        "repairs": sum(1 for e in log if e.get("kind") == "repair"),
        "tokens": run["tokens"],
        "decision": None,
        "weekly": weekly,
        "snippets": snippets[:6],
        "citations": [
            {k: p[k] for k in ("url", "access_ts", "sha256")}
            for p in tools.pages.values()
        ],
        "reference": ref,
    }
    if not final:
        result["checks"] = {"final_answer": False}
        return result
    pay, member, be = (
        final["pay_per_use_total"],
        final["membership_total"],
        final["break_even_rides"],
    )
    fee = _membership_fee(snippets)
    result.update(
        {
            "decision": final["decision"],
            "pay_per_use_total": pay,
            "membership_total": member,
            "membership_fee": fee,
            "membership_residual": round(member - fee, 2) if fee else None,
            "break_even_rides": be,
            "actual_rides": sum(int(r["rides"]) for r in weekly) or None,
            "justification": final["justification"],
            "assumptions": final.get("assumptions", []),
        }
    )
    lower_member = member < pay
    result["checks"] = {
        "final_answer": True,
        "numbers_from_calculator": all(
            any(_close(x, c) for c in calcs) for x in (pay, member, be)
        ),
        "decision_matches_totals": (final["decision"] == bike_costs.DECISION_MEMBER)
        == lower_member,
        "matches_reference": final["decision"] == ref["decision"]
        and _close(pay, ref["pay_total"], 0.06)
        and _close(member, ref["member_total"], 0.06),
        "used_policy_page": bool(tools.pages),
    }
    return result


def run_scenario(
    csv_path: str,
    rider_id: str,
    url: str,
    label: Optional[str] = None,
    *,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    chat_fn: Callable[..., Dict[str, Any]] = llm.chat,
    fetch: Callable[[str], Dict[str, str]] = bike_policy.fetch_page,
    raw_dir: Path = RAW_DIR,
    save: bool = True,
    **agent_kwargs: Any,
) -> Dict[str, Any]:
    label = label or Path(csv_path).stem
    tools = BikeTools(csv_path, fetch=fetch)
    run = bike_agent.run_bike_agent(
        tools, url, rider_id, chat_fn=chat_fn, on_event=on_event, **agent_kwargs
    )
    result = summarize(run, tools, csv_path, rider_id)
    result["label"] = label
    result["csv_sha256"] = file_sha256(csv_path)
    result["csv_rows"] = tools.db.row_count
    if save:
        save_run(label, run, result, tools, Path(raw_dir))
    return result


def save_run(
    label: str,
    run: Dict[str, Any],
    result: Dict[str, Any],
    tools: BikeTools,
    raw_dir: Path,
) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for page in tools.pages.values():
        (raw_dir / f"pricing_snapshot_{label}.txt").write_text(
            page["text"] + "\n", encoding="utf-8"
        )
        meta = {k: page[k] for k in ("url", "access_ts", "sha256")}
        meta["note"] = "sha256 is of the extracted page text in the .txt file"
        (raw_dir / f"pricing_snapshot_{label}.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
        break
    timeline = [
        {k: v for k, v in e.items() if k != "full_observation"} for e in run["log"]
    ]
    (raw_dir / f"bike_{label}_run.json").write_text(
        json.dumps({"result": result, "timeline": timeline}, indent=2, default=str)
        + "\n",
        encoding="utf-8",
    )
