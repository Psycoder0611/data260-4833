"""Summarize JMeter result files (JTL CSV or the listener's "Save Table Data" CSV).

Three layouts are accepted:
  * JTL (Simple Data Writer): columns ``timeStamp, elapsed, label, success, ...``
  * "Save Table Data" from Results Tree / Aggregate listeners: one row per
    sample with ``Sample #, Start Time, Thread Name, Label, Sample Time(ms),
    Status, ...`` (column names vary a little between JMeter versions).
  * "Save Table Data" from the Aggregate Report: already a summary, one row per
    label plus TOTAL, with ``# Samples, Average, Median, 90% Line, 95% Line,
    99% Line, Min, Max, Error %, Throughput``.
"""

import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

ELAPSED_NAMES = ("elapsed", "sample time(ms)", "sample time", "time")
START_NAMES = ("timestamp", "start time", "timestamp(ms)")
OK_NAMES = ("success", "status")


def _pick(row: Dict[str, str], names: tuple) -> Optional[str]:
    """Value of the first column whose lower-cased name is in names."""
    for key, value in row.items():
        if key and key.strip().lower() in names:
            return value
    return None


def _ok(value: Optional[str]) -> bool:
    """True for 'true', 'success', 'ok' or a 2xx status text."""
    text = (value or "").strip().lower()
    return text in ("true", "success", "ok", "1")


def percentile(sorted_values: List[float], pct: float) -> float:
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return float(sorted_values[rank - 1])


def _to_ms(text: str) -> Optional[float]:
    """Parse an epoch-ms number (the table export may use a clock time: skipped)."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _num(row: Dict[str, str], name: str) -> float:
    """Number in a column of the aggregate table ('0.000%' and '10.1/sec' ok)."""
    text = (row.get(name) or "").strip().lower()
    for suffix in ("%", "/sec", "/min"):
        text = text.replace(suffix, "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _summarize_aggregate(path: Path, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Use the TOTAL row (or the last row) of an Aggregate Report export."""
    total = rows[-1]
    for row in rows:
        if (row.get("Label") or "").upper() == "TOTAL":
            total = row
    count = int(_num(total, "# Samples"))
    errors = round(count * _num(total, "Error %") / 100)
    return {
        "file": path.name,
        "samples": count,
        "average_ms": _num(total, "Average"),
        "min_ms": _num(total, "Min"),
        "max_ms": _num(total, "Max"),
        "median_ms": _num(total, "Median"),
        "p90_ms": _num(total, "90% Line"),
        "p95_ms": _num(total, "95% Line"),
        "p99_ms": _num(total, "99% Line"),
        "error_count": errors,
        "error_pct": round(_num(total, "Error %"), 2),
        "throughput_per_sec": round(_num(total, "Throughput"), 2) or None,
    }


def summarize(path: Path) -> Dict[str, Any]:
    """Read one result CSV and return samples, timings, error rate and throughput."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if rows and "# Samples" in rows[0]:
        return _summarize_aggregate(path, rows)
    times: List[float] = []
    errors = 0
    starts: List[float] = []
    ends: List[float] = []
    for row in rows:
        elapsed = _to_ms(_pick(row, ELAPSED_NAMES) or "")
        if elapsed is None:
            continue
        times.append(elapsed)
        if not _ok(_pick(row, OK_NAMES)):
            errors += 1
        start = _to_ms(_pick(row, START_NAMES) or "")
        if start is not None:
            starts.append(start)
            ends.append(start + elapsed)
    ordered = sorted(times)
    count = len(ordered)
    span = (max(ends) - min(starts)) / 1000 if starts and max(ends) > min(starts) else 0
    return {
        "file": path.name,
        "samples": count,
        "average_ms": round(sum(ordered) / count, 1) if count else 0.0,
        "min_ms": min(ordered) if count else 0.0,
        "max_ms": max(ordered) if count else 0.0,
        "median_ms": percentile(ordered, 50),
        "p90_ms": percentile(ordered, 90),
        "p95_ms": percentile(ordered, 95),
        "p99_ms": percentile(ordered, 99),
        "error_count": errors,
        "error_pct": round(100 * errors / count, 2) if count else 0.0,
        "throughput_per_sec": round(count / span, 2) if span else None,
    }
