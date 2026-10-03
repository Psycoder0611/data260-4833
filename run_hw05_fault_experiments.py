import csv
import json
import math
import random
import statistics
import time
from pathlib import Path

from retry_utils import run_with_retry


# ---------------------------------------------------------
# PERSONAL CONFIGURATION
# ---------------------------------------------------------

VERIFY_SEED = 264833

FAILURE_RATES = [
    0.0,
    0.2,
    0.5,
]

CALLS_PER_RATE = 50

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 2.0
BASE_DELAY = 0.01


# ---------------------------------------------------------
# OUTPUT PATHS
# ---------------------------------------------------------

RAW_DIR = Path("reports/hw05/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = RAW_DIR / "fault_injection_calls.csv"
METRICS_JSON = RAW_DIR / "fault_metrics.json"


# ---------------------------------------------------------
# P99 HELPER
# ---------------------------------------------------------

def percentile_99(values):
    ordered = sorted(values)

    index = math.ceil(
        0.99 * len(ordered)
    ) - 1

    return ordered[index]


# ---------------------------------------------------------
# ONE EXPERIMENT RATE
# ---------------------------------------------------------

def run_failure_rate(
    failure_rate,
    calls=CALLS_PER_RATE
):
    """
    Run deterministic simulated storage calls.

    Each attempt independently fails according to the
    configured injected failure rate.

    VERIFY_SEED makes the sequence reproducible.
    """

    rate_seed = (
        VERIFY_SEED
        + int(failure_rate * 1000)
    )

    rng = random.Random(rate_seed)

    rows = []

    for call_index in range(1, calls + 1):

        attempt_events = []

        def simulated_storage_operation():
            should_fail = (
                rng.random() < failure_rate
            )

            attempt_events.append(
                "FAIL"
                if should_fail
                else "SUCCESS"
            )

            if should_fail:
                raise RuntimeError(
                    "simulated transient storage failure"
                )

            return {
                "message": "storage operation succeeded"
            }

        start_time = time.perf_counter()

        result = run_with_retry(
            simulated_storage_operation,
            max_attempts=MAX_ATTEMPTS,
            timeout_seconds=TIMEOUT_SECONDS,
            base_delay=BASE_DELAY,
        )

        latency_ms = (
            time.perf_counter() - start_time
        ) * 1000

        rows.append(
            {
                "verify_seed": VERIFY_SEED,
                "failure_rate": failure_rate,
                "call_index": call_index,
                "success": result["ok"],
                "attempts": result["attempts"],
                "attempt_events": "|".join(
                    attempt_events
                ),
                "latency_ms": round(
                    latency_ms,
                    3
                ),
                "error": result["error"] or "",
            }
        )

    return rows


# ---------------------------------------------------------
# METRICS
# ---------------------------------------------------------

def summarize(rows):
    successful = sum(
        1
        for row in rows
        if row["success"]
    )

    latencies = [
        row["latency_ms"]
        for row in rows
    ]

    return {
        "calls": len(rows),
        "success_rate_percent": round(
            successful / len(rows) * 100,
            2,
        ),
        "mean_latency_ms": round(
            statistics.mean(latencies),
            3,
        ),
        "p99_latency_ms": round(
            percentile_99(latencies),
            3,
        ),
    }


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    all_rows = []
    metrics = {}

    print(
        f"VERIFY_SEED = {VERIFY_SEED}"
    )

    print(
        f"Calls per failure rate = "
        f"{CALLS_PER_RATE}"
    )

    print(
        f"Maximum attempts = "
        f"{MAX_ATTEMPTS}"
    )

    print()

    for failure_rate in FAILURE_RATES:

        rows = run_failure_rate(
            failure_rate
        )

        all_rows.extend(rows)

        summary = summarize(rows)

        label = (
            f"{int(failure_rate * 100)}%"
        )

        metrics[label] = summary

        print("=" * 70)
        print(
            f"INJECTED FAILURE RATE: "
            f"{label}"
        )
        print("=" * 70)

        print(
            f"Calls: "
            f"{summary['calls']}"
        )

        print(
            f"Success rate: "
            f"{summary['success_rate_percent']}%"
        )

        print(
            f"Mean latency: "
            f"{summary['mean_latency_ms']} ms"
        )

        print(
            f"P99 latency: "
            f"{summary['p99_latency_ms']} ms"
        )

        print()

    # Save all 150 raw call records.
    with RAW_CSV.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        fieldnames = [
            "verify_seed",
            "failure_rate",
            "call_index",
            "success",
            "attempts",
            "attempt_events",
            "latency_ms",
            "error",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(all_rows)

    # Save summary metrics.
    with METRICS_JSON.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metrics,
            file,
            indent=2
        )

    print(
        f"Raw records saved to: {RAW_CSV}"
    )

    print(
        f"Metrics saved to: {METRICS_JSON}"
    )

    print(
        f"Total raw call records: "
        f"{len(all_rows)}"
    )


if __name__ == "__main__":
    main()