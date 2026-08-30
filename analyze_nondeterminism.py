import json
import statistics
from collections import Counter
from pathlib import Path


RAW_DIR = Path("reports/hw01/raw")
OUTPUT_FILE = Path("reports/hw01/METRICS.md")

TEMPERATURES = [0.7, 0.0]


def load_runs(temperature):
    """
    Load all saved runs for one temperature.
    """
    folder = RAW_DIR / f"t{temperature:.1f}"
    run_files = sorted(folder.glob("run_*.json"))

    runs = []

    for file_path in run_files:
        with open(file_path, "r", encoding="utf-8") as file:
            runs.append(json.load(file))

    return runs


def percentile(values, percent):
    """
    Calculate a percentile from latency values.
    """
    if not values:
        return 0

    sorted_values = sorted(values)

    index = round(
        (percent / 100) * (len(sorted_values) - 1)
    )

    return sorted_values[index]


def analyze_temperature(temperature):
    """
    Calculating the metrics required by the assignment
    """
    runs = load_runs(temperature)

    latencies = [
        run["latency_ms"]
        for run in runs
    ]

    tag_sets = [
        tuple(run["final_tags"])
        for run in runs
    ]

    distinct_tag_sets = len(set(tag_sets))

    # Counts how many runs contain each individual tag
    tag_counts = Counter()

    for run in runs:
        unique_tags = set(run["final_tags"])

        for tag in unique_tags:
            tag_counts[tag] += 1

    tags_in_all_runs = sorted([
        tag
        for tag, count in tag_counts.items()
        if count == len(runs)
    ])

    tags_in_one_run = sorted([
        tag
        for tag, count in tag_counts.items()
        if count == 1
    ])

    return {
        "temperature": temperature,
        "runs": len(runs),
        "distinct_tag_sets": distinct_tag_sets,
        "tags_in_all_runs": tags_in_all_runs,
        "tags_in_one_run": tags_in_one_run,
        "p50_latency_ms": percentile(latencies, 50),
        "p95_latency_ms": percentile(latencies, 95),
        "p99_latency_ms": percentile(latencies, 99),
    }


def main():
    results = []

    for temperature in TEMPERATURES:
        results.append(
            analyze_temperature(temperature)
        )

    for result in results:
        print(
            f"\nTemperature: {result['temperature']}"
        )
        print(
            f"Runs: {result['runs']}"
        )
        print(
            f"Distinct tag sets: "
            f"{result['distinct_tag_sets']}"
        )
        print(
            f"Tags in all 20 runs: "
            f"{result['tags_in_all_runs']}"
        )
        print(
            f"Tags in exactly 1 run: "
            f"{result['tags_in_one_run']}"
        )
        print(
            f"P50 latency: "
            f"{result['p50_latency_ms']:.2f} ms"
        )
        print(
            f"P95 latency: "
            f"{result['p95_latency_ms']:.2f} ms"
        )
        print(
            f"P99 latency: "
            f"{result['p99_latency_ms']:.2f} ms"
        )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "# Non-Determinism Experiment Metrics\n\n"
        )
        file.write("Model: `qwen3:8b`\n\n")
        file.write(
            "Fixed input: "
            "`reports/hw01/cases/nondeterminism_input.json`\n\n"
        )

        file.write(
            "| Metric | Temp 0.7 | Temp 0.0 |\n"
        )
        file.write(
            "|---|---|---|\n"
        )

        r07 = results[0]
        r00 = results[1]

        file.write(
            f"| Distinct tag sets | "
            f"{r07['distinct_tag_sets']} | "
            f"{r00['distinct_tag_sets']} |\n"
        )

        file.write(
            f"| Tags in all 20 runs | "
            f"{', '.join(r07['tags_in_all_runs']) or 'None'} | "
            f"{', '.join(r00['tags_in_all_runs']) or 'None'} |\n"
        )

        file.write(
            f"| Tags in exactly 1 run | "
            f"{', '.join(r07['tags_in_one_run']) or 'None'} | "
            f"{', '.join(r00['tags_in_one_run']) or 'None'} |\n"
        )

        file.write(
            f"| Latency p50 (ms) | "
            f"{r07['p50_latency_ms']:.2f} | "
            f"{r00['p50_latency_ms']:.2f} |\n"
        )

        file.write(
            f"| Latency p95 (ms) | "
            f"{r07['p95_latency_ms']:.2f} | "
            f"{r00['p95_latency_ms']:.2f} |\n"
        )

        file.write(
            f"| Latency p99 (ms) | "
            f"{r07['p99_latency_ms']:.2f} | "
            f"{r00['p99_latency_ms']:.2f} |\n"
        )

    print(
        f"\nMetrics written to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()