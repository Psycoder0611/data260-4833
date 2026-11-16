# ruff: noqa: E501
"""Numbers for the dashboard and the report: percentiles, latency shares, judge validation.

Pure functions over span dicts and score lists, so they are easy to test.
"""

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy import stats as sps

from hw10 import tracing

# Stages of the cache-miss table (name -> spans that make it up)
MISS_TABLE = [
    ("Cache lookup", (tracing.CACHE_LOOKUP,)),
    ("Planner", (tracing.PLANNER,)),
    ("Writer", (tracing.WRITER,)),
    ("Reviewer", (tracing.REVIEWER,)),
    ("Queue wait (total)", tracing.QUEUE_STAGES),
    ("Evaluation", (tracing.EVALUATION,)),
]


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    """q-th percentile (linear interpolation); None for an empty list."""
    return round(float(np.percentile(values, q)), 1) if len(values) else None


def stage_ms(spans: List[Dict[str, Any]], stages: Sequence[str]) -> float:
    """Sum of duration_ms of the spans of these stages in one trace.

    For a stage that was retried only the successful attempt counts as work; the failed
    attempts of the same stage are included too because the request really waited for them.
    """
    return round(sum(s["duration_ms"] for s in spans if s["stage"] in stages), 1)


def miss_latency_table(traces: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """p50, p95 and mean share of the cache-miss pipeline time for each stage.

    End-to-end here = cache lookup + queue waits + Planner + Writer + Reviewer +
    Evaluation (the whole path of a miss through the pipeline including the evaluator).
    Share of one request = stage time / that request's end-to-end; the table reports the
    share of the summed time over all requests (sum of stage / sum of end-to-end), which
    is not distorted by a few short requests.
    """
    rows, totals = [], []
    per_stage: Dict[str, List[float]] = {name: [] for name, _ in MISS_TABLE}
    for spans in traces.values():
        values = {name: stage_ms(spans, stages) for name, stages in MISS_TABLE}
        total = sum(values.values())
        if total <= 0:
            continue
        totals.append(total)
        for name, value in values.items():
            per_stage[name].append(value)
    grand = float(sum(totals)) or 1.0
    for name, _ in MISS_TABLE:
        series = per_stage[name]
        rows.append(
            {
                "stage": name,
                "p50_ms": percentile(series, 50),
                "p95_ms": percentile(series, 95),
                "share_pct": round(100 * sum(series) / grand, 1) if series else None,
            }
        )
    rows.append(
        {
            "stage": "End-to-end (all stages above)",
            "p50_ms": percentile(totals, 50),
            "p95_ms": percentile(totals, 95),
            "share_pct": 100.0 if totals else None,
        }
    )
    user_facing = [
        s["duration_ms"]
        for spans in traces.values()
        for s in spans
        if s["stage"] == tracing.REQUEST
    ]
    return {
        "n": len(totals),
        "rows": rows,
        "user_facing_p50_ms": percentile(user_facing, 50),
        "user_facing_p95_ms": percentile(user_facing, 95),
    }


def summary_metrics(traces: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Dashboard Summary numbers from a set of traces (already filtered by time window)."""
    requests = {t: s for t, s in traces.items() if any(x["stage"] == tracing.REQUEST for x in s)}
    hits = [t for t, s in requests.items() if tracing.trace_path(s) == "hit"]
    misses = [t for t, s in requests.items() if tracing.trace_path(s) == "miss"]
    errors = [t for t, s in requests.items() if tracing.trace_status(s) == "error"]

    def lat(ids):
        return [
            x["duration_ms"] for t in ids for x in requests[t] if x["stage"] == tracing.REQUEST
        ]

    n = len(requests)
    return {
        "requests": n,
        "hits": len(hits),
        "misses": len(misses),
        "hit_rate_pct": round(100 * len(hits) / n, 1) if n else None,
        "miss_rate_pct": round(100 * len(misses) / n, 1) if n else None,
        "errors": len(errors),
        "error_rate_pct": round(100 * len(errors) / n, 1) if n else None,
        "latency_all": {"p50": percentile(lat(requests), 50), "p95": percentile(lat(requests), 95)},
        "latency_hit": {"p50": percentile(lat(hits), 50), "p95": percentile(lat(hits), 95)},
        "latency_miss": {"p50": percentile(lat(misses), 50), "p95": percentile(lat(misses), 95)},
    }


def validation_stats(human: Sequence[float], judge: Sequence[Optional[float]]) -> Dict[str, Any]:
    """Spearman and mean absolute difference between human labels and judge scores.

    Cases where the judge has no score are left out and counted in "n_missing".
    """
    pairs = [(h, j) for h, j in zip(human, judge) if j is not None]
    out: Dict[str, Any] = {"n": len(pairs), "n_missing": len(human) - len(pairs)}
    if len(pairs) < 3:
        return {**out, "spearman": None, "p_value": None, "mad": None}
    h = np.array([p[0] for p in pairs], dtype=float)
    j = np.array([p[1] for p in pairs], dtype=float)
    if np.ptp(h) == 0 or np.ptp(j) == 0:
        rho, p = None, None  # a constant series has no rank correlation
    else:
        result = sps.spearmanr(h, j)
        rho, p = round(float(result.statistic), 3), round(float(result.pvalue), 4)
    return {
        **out,
        "spearman": rho,
        "p_value": p,
        "mad": round(float(np.mean(np.abs(h - j))), 3),
        "mean_bias": round(float(np.mean(j - h)), 3),
        "exact_agreement_pct": round(100 * float(np.mean(h == j)), 1),
        "within_one_pct": round(100 * float(np.mean(np.abs(h - j) <= 1)), 1),
    }


def repeatability(runs: List[Dict[str, Optional[float]]]) -> Dict[str, Any]:
    """How much the judge's score moves when the same inputs are judged again.

    runs: one {case_id: score} dict per run. For each case the change is
    max(score) - min(score) over the runs (0 = identical in every run).
    """
    cases = sorted(set.intersection(*[set(r) for r in runs])) if runs else []
    changes, changed = [], 0
    for case in cases:
        scores = [r[case] for r in runs if r[case] is not None]
        if len(scores) < len(runs):
            continue
        spread = max(scores) - min(scores)
        changes.append(spread)
        changed += spread > 0
    n = len(changes)
    return {
        "runs": len(runs),
        "cases": n,
        "cases_changed": changed,
        "fraction_changed": round(changed / n, 3) if n else None,
        "mean_abs_change": round(float(np.mean(changes)), 3) if n else None,
        "max_abs_change": float(max(changes)) if n else None,
        "per_case_spread": dict(zip(cases, changes)),
    }
