import csv
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import event

from database import engine
from main import app


PAGE_SIZES = [10, 50, 200]
RUNS_PER_CASE = 30

OUTPUT_DIR = Path("reports/hw04/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RAW_FILE = OUTPUT_DIR / "nplus1_raw.csv"


query_count = 0
measurement_active = False


@event.listens_for(engine, "before_cursor_execute")
def count_sql_queries(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany
):
    global query_count

    if measurement_active:
        query_count += 1


def percentile(values, percentile_value):
    return float(
        np.percentile(values, percentile_value)
    )


def run_benchmark():
    global query_count
    global measurement_active

    client = TestClient(app)

    login_response = client.post(
        "/api/login",
        json={
            "email": "admin@example.com",
            "password": "password123"
        }
    )

    if login_response.status_code != 200:
        raise RuntimeError(
            f"Login failed: {login_response.text}"
        )

    print("Login successful.")
    print("Starting N+1 benchmark...")
    print()

    raw_rows = []

    versions = {
        "naive": "/api/hw4/trials/naive",
        "fixed": "/api/hw4/trials/fixed"
    }

    for page_size in PAGE_SIZES:
        for version, endpoint in versions.items():

            latencies = []
            sql_counts = []

            print(
                f"Running {version}, "
                f"page_size={page_size}"
            )

            for run_number in range(
                1,
                RUNS_PER_CASE + 1
            ):
                query_count = 0

                measurement_active = True

                start_time = time.perf_counter()

                response = client.get(
                    endpoint,
                    params={
                        "page_size": page_size
                    }
                )

                end_time = time.perf_counter()

                measurement_active = False

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Request failed: "
                        f"{response.status_code} "
                        f"{response.text}"
                    )

                latency_ms = (
                    end_time - start_time
                ) * 1000

                latencies.append(latency_ms)
                sql_counts.append(query_count)

                raw_rows.append(
                    {
                        "version": version,
                        "page_size": page_size,
                        "run": run_number,
                        "sql_statements": query_count,
                        "latency_ms": round(
                            latency_ms,
                            3
                        )
                    }
                )

            print(
                f"  SQL statements/request: "
                f"{sql_counts[0]}"
            )

            print(
                f"  p50: "
                f"{percentile(latencies, 50):.3f} ms"
            )

            print(
                f"  p95: "
                f"{percentile(latencies, 95):.3f} ms"
            )

            print(
                f"  p99: "
                f"{percentile(latencies, 99):.3f} ms"
            )

            print()

    with RAW_FILE.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "version",
                "page_size",
                "run",
                "sql_statements",
                "latency_ms"
            ]
        )

        writer.writeheader()
        writer.writerows(raw_rows)

    print(
        f"Saved {len(raw_rows)} raw requests "
        f"to {RAW_FILE}"
    )


if __name__ == "__main__":
    run_benchmark()