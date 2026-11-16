# ruff: noqa: E501
"""Loading and shaping the data behind the Streamlit pages (no Streamlit import here).

Data sources (all written by my own runs, nothing is invented for the dashboard):
  spans.jsonl                  one span per pipeline stage            (Part 4 tracing)
  part2_eval.json              evaluator records of the Part 2 questions
  part4_latency_runs.jsonl     one line per cache-miss run: spans summary + evaluator record
  part4_traces.json            the three named traces (hit, miss, failed)
  part3_validation.json        Spearman, MAD, repeatability, per-case rows
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from hw10 import config, stats, tracing

WINDOWS = {
    "Last 15 minutes": 15 * 60,
    "Last hour": 3600,
    "Last 24 hours": 24 * 3600,
    "Last 7 days": 7 * 24 * 3600,
    "All logged requests": None,
}


def raw_path(name: str) -> Path:
    """Path of a raw result file (read at call time so tests can redirect it)."""
    return config.RAW_DIR / name


def read_json(path: Path) -> Optional[Any]:
    """Parsed JSON file, or None if it is missing or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Lines of a JSON-lines file that parse; [] if the file is missing."""
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return rows


def traces_in_window(
    spans: List[Dict[str, Any]], window_seconds: Optional[int], now: Optional[float] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Traces whose request (or first) span started inside the window."""
    grouped = tracing.group_by_trace(spans)
    if window_seconds is None:
        return grouped
    cutoff = (now or time.time()) - window_seconds
    keep = {}
    for tid, items in grouped.items():
        anchor = next((s for s in items if s["stage"] == tracing.REQUEST), items[0])
        if tracing.parse_iso(anchor["start"]) >= cutoff:
            keep[tid] = items
    return keep


def stage_sorted(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Spans in pipeline stage order (retries of one stage stay in time order)."""
    rank = {name: i for i, name in enumerate(tracing.STAGE_ORDER)}
    return sorted(spans, key=lambda s: (rank.get(s["stage"], 99), s["start"]))


def span_table(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows for the trace-lookup table, one per span, in stage order."""
    rows = []
    for s in stage_sorted(spans):
        rows.append(
            {
                "stage": s["stage"],
                "start": s["start"],
                "end": s["end"],
                "duration_ms": s["duration_ms"],
                "status": s["status"],
                "error": s.get("error") or "",
                "component": s.get("component", ""),
                "details": json.dumps(s.get("attrs") or {}, default=str),
            }
        )
    return rows


def path_description(spans: List[Dict[str, Any]]) -> str:
    """One line that says which path the request took."""
    kind = tracing.trace_path(spans)
    names = [s["stage"] for s in spans if s["stage"] != tracing.REQUEST]
    if kind == "hit":
        return "CACHE HIT path: answered from the semantic cache; the Kafka pipeline was not used. Stages: " + " -> ".join(names)
    if kind == "miss":
        if tracing.trace_status(spans) == "error":
            return "CACHE MISS path: sent to the Kafka pipeline but the request failed and was dead-lettered. Stages: " + " -> ".join(names)
        return "CACHE MISS path: went through Planner, Writer and Reviewer over Kafka. Stages: " + " -> ".join(names)
    return "Path unknown (no cache_lookup span). Stages: " + " -> ".join(names)


def evaluation_records() -> List[Dict[str, Any]]:
    """Every evaluator record from Part 2 and from the Part 4 runs (one per trace)."""
    records: Dict[str, Dict[str, Any]] = {}
    part2 = read_json(raw_path("part2_eval.json")) or {}
    for rec in part2.get("records", []):
        records[rec["trace_id"]] = {**rec, "source": "Part 2"}
    for run in read_jsonl(raw_path("part4_latency_runs.jsonl")):
        rec = run.get("evaluation")
        if rec:
            records[rec["trace_id"]] = {**rec, "source": "Part 4 run"}
    return list(records.values())


def stage_means(records: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Mean judge score per pipeline stage (scored traces only)."""
    def mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 2) if values else None

    return {
        "Planner: plan quality": mean(r["plan_quality"]["score"] for r in records),
        "Writer: draft helpfulness": mean(r["writer_helpfulness"]["score"] for r in records),
        "Reviewer: final helpfulness": mean(r["final_helpfulness"]["score"] for r in records),
    }


def coordination_text(records: List[Dict[str, Any]]) -> str:
    """Short, number-based reading of how Planner, Writer and Reviewer worked together."""
    scored = [
        r for r in records
        if r["plan_quality"]["score"] is not None and r["writer_helpfulness"]["score"] is not None
    ]
    if not scored:
        return "No scored traces yet. Run the evaluator (Part 2) first."
    means = stage_means(scored)
    plan = [r["plan_quality"]["score"] for r in scored]
    draft = [r["writer_helpfulness"]["score"] for r in scored]
    diffs = [r["improvement"]["difference"] for r in scored if r["improvement"]["difference"] is not None]
    same = sum(1 for r in scored if r["improvement"].get("same_text"))
    rejected = sum(1 for r in scored if (r.get("reviewer") or {}).get("status") == "rejected")
    parts = [
        f"{len(scored)} scored traces. Mean plan quality {means['Planner: plan quality']}, mean draft helpfulness "
        f"{means['Writer: draft helpfulness']}, mean final helpfulness {means['Reviewer: final helpfulness']}."
    ]
    corr = stats.validation_stats(plan, draft)
    if corr["spearman"] is not None:
        parts.append(
            f"Plan quality and draft helpfulness have Spearman {corr['spearman']} (n={corr['n']}), so "
            + ("a better plan tends to come with a more helpful draft." if corr["spearman"] >= 0.3
               else "the plan score says little about how helpful the draft turns out." if corr["spearman"] > -0.3
               else "plan quality moves against draft helpfulness, which is unexpected.")
        )
    if diffs:
        better = sum(d > 0 for d in diffs)
        worse = sum(d < 0 for d in diffs)
        parts.append(
            f"Final vs draft: {better} traces improved, {worse} got worse, {len(diffs) - better - worse} unchanged "
            f"(mean difference {sum(diffs) / len(diffs):+.2f}). In {same} of {len(scored)} traces the final text is identical "
            f"to the draft: the Reviewer approves or rejects ({rejected} rejected) but does not rewrite, so it cannot raise helpfulness."
        )
    return " ".join(parts)
