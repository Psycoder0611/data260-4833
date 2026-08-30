import json
import subprocess
import time
import csv
from pathlib import Path


# Model chosen for the repeated experiment.
# qwen3:8b and qwen3:4b were too slow on the local machine.
MODEL = "qwen3:8b"

# No. of runs required by the assignment for each temperature.
RUNS_PER_TEMPERATURE = 20

# Temperatures required in the assignment.
TEMPERATURES = [0.7, 0.0]

# Fixed input file used for every run.
INPUT_FILE = Path(
    "reports/hw01/cases/nondeterminism_input.json"
)

# Folder where raw experiment outputs will be stored.
RAW_DIR = Path(
    "reports/hw01/raw"
)

# TSV file containing latency and final tag results.
METRICS_FILE = RAW_DIR / "metrics.tsv"


def load_fixed_input():
    """
    Read the same fixed title, content, and email
    that will be reused for all 40 experiment runs.
    """

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_publish_package(stdout_text):
    """
    Extract the final Publish Package JSON
    printed by agents_demo.py.
    """

    marker = "Publish Package"

    # Find the last Publish Package section.
    marker_position = stdout_text.rfind(marker)

    if marker_position == -1:
        raise ValueError(
            "Could not find Publish Package in agents_demo.py output."
        )

    # Find the first { after the marker.
    json_start = stdout_text.find("{", marker_position)

    if json_start == -1:
        raise ValueError(
            "Could not find JSON after Publish Package."
        )

    json_text = stdout_text[json_start:].strip()

    return json.loads(json_text)


def run_once(fixed_input, temperature, run_number):
    """
    Run agents_demo.py once and return:
    - end-to-end latency
    - final tags
    - full console output
    - final publish package
    """

    command = [
        "python",
        "agents_demo.py",

        "--title",
        fixed_input["title"],

        "--content",
        fixed_input["content"],

        "--email",
        fixed_input["email"],

        "--model",
        MODEL,

        "--temperature",
        str(temperature),

        "--strict",
    ]

    print(
        f"Running temperature={temperature}, "
        f"run={run_number}/{RUNS_PER_TEMPERATURE}"
    )

    # Start end-to-end timer.
    start_time = time.perf_counter()

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    # Stop timer after Planner, Reviewer and Finalizer finish.
    end_time = time.perf_counter()

    latency_ms = round(
        (end_time - start_time) * 1000,
        2
    )

    # If agents_demo.py failed, preserve the error.
    if result.returncode != 0:
        raise RuntimeError(
            "agents_demo.py failed.\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    # Extract final Publish Package JSON.
    package = extract_publish_package(
        result.stdout
    )

    # Get final tags.
    final_tags = (
        package
        .get("agents", {})
        .get("final", {})
        .get("tags", [])
    )

    return {
        "temperature": temperature,
        "run": run_number,
        "latency_ms": latency_ms,
        "tags": final_tags,
        "package": package,
        "stdout": result.stdout,
    }


def save_raw_result(result):
    """
    Save one complete run under:

    reports/hw01/raw/t0.7/

    or

    reports/hw01/raw/t0.0/
    """

    temperature = result["temperature"]

    # Folder name required for each temperature.
    folder = RAW_DIR / f"t{temperature:.1f}"

    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = folder / (
        f"run_{result['run']:02d}.json"
    )

    raw_data = {
        "temperature": result["temperature"],
        "run": result["run"],
        "model": MODEL,
        "latency_ms": result["latency_ms"],
        "final_tags": result["tags"],
        "publish_package": result["package"],
        "console_output": result["stdout"],
    }

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            raw_data,
            file,
            indent=2,
            ensure_ascii=False
        )


def load_existing_result(output_file):
    """
    Read a previously completed run so it can still
    be included in metrics.tsv after resuming.
    """

    with open(output_file, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    return {
        "temperature": raw_data.get("temperature"),
        "run": raw_data.get("run"),
        "latency_ms": raw_data.get("latency_ms"),
        "tags": raw_data.get("final_tags", []),
    }


def main():

    # Read the single fixed experiment input.
    fixed_input = load_fixed_input()

    # Create raw output directory.
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    metric_rows = []

    # Run both temperature conditions.
    for temperature in TEMPERATURES:

        print(
            f"\nStarting temperature {temperature}"
        )

        for run_number in range(
            1,
            RUNS_PER_TEMPERATURE + 1
        ):

            # Check whether this run was already completed.
            output_folder = RAW_DIR / f"t{temperature:.1f}"
            output_file = output_folder / f"run_{run_number:02d}.json"

            if output_file.exists():

                print(
                    f"Skipping temperature={temperature}, "
                    f"run={run_number} because output already exists."
                )

                # Read the existing run so it is still added to metrics.tsv.
                existing_result = load_existing_result(output_file)

                metric_rows.append({
                    "temperature": existing_result["temperature"],
                    "run": existing_result["run"],
                    "latency_ms": existing_result["latency_ms"],
                    "tags_json": json.dumps(
                        existing_result["tags"],
                        ensure_ascii=False
                    ),
                    "status": "success",
                })

                continue

            try:

                result = run_once(
                    fixed_input,
                    temperature,
                    run_number
                )

                # Save full raw output.
                save_raw_result(result)

                # Save summary information for metrics.tsv.
                metric_rows.append({
                    "temperature": temperature,
                    "run": run_number,
                    "latency_ms": result["latency_ms"],
                    "tags_json": json.dumps(
                        result["tags"],
                        ensure_ascii=False
                    ),
                    "status": "success",
                })

                print(
                    f"Completed: "
                    f"{result['latency_ms']} ms | "
                    f"Tags: {result['tags']}"
                )

            except Exception as error:

                print(
                    f"Run failed: {error}"
                )

                metric_rows.append({
                    "temperature": temperature,
                    "run": run_number,
                    "latency_ms": "",
                    "tags_json": "",
                    "status": "failed",
                })

    # Write all 40 experiment results into metrics.tsv.
    with open(
        METRICS_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "temperature",
                "run",
                "latency_ms",
                "tags_json",
                "status",
            ],
            delimiter="\t",
        )

        writer.writeheader()
        writer.writerows(metric_rows)

    print(
        "\nExperiment complete."
    )

    print(
        f"Metrics saved to: {METRICS_FILE}"
    )

    print(
        f"Raw outputs saved under: {RAW_DIR}"
    )


if __name__ == "__main__":
    main()