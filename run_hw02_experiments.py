import csv
import json
import time
from pathlib import Path
from typing import Dict, Any

from agent_graph import (
    AgentState,
    PlannerOutput,
    build_graph
)

from src.model_client import ModelClient


# ---------------------------------------------------------
# Personal HW2 configuration
# ---------------------------------------------------------

SID4 = 4833
SEED = 4833
VERIFY_SEED = 260000 + SID4

MODEL_NAME = "qwen3:8b"

BASE_DIR = Path("reports/hw02")

RAW_DIR = BASE_DIR / "raw"

CASE_DIR = BASE_DIR / "cases"

SCHEMA_INPUT_PATH = (
    CASE_DIR / "schema_input.json"
)


# I am making sure the required experiment folders exist.
RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)

CASE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ---------------------------------------------------------
# Load frozen input
# ---------------------------------------------------------

def load_frozen_input() -> Dict[str, Any]:
    """
    I am loading the same frozen input for every
    schema and ceiling experiment.
    """

    with open(
        SCHEMA_INPUT_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ---------------------------------------------------------
# Run one graph experiment
# ---------------------------------------------------------

def run_once(
    case: Dict[str, Any],
    turn_ceiling: int
) -> Dict[str, Any]:
    """
    I am running the graph once and collecting
    the final state, latency and retry outcome.
    """

    llm = ModelClient(
        model=MODEL_NAME,
        temperature=0.0
    )

    graph = build_graph()


    initial_state: AgentState = {

        "title":
            case["title"],

        "content":
            case["content"],

        "email":
            case["email"],

        "strict":
            case.get(
                "strict",
                True
            ),

        "task":
            (
                "Generate exactly three topical tags and "
                "a summary of no more than 25 words."
            ),

        "llm":
            llm,

        "planner_proposal":
            {},

        "reviewer_feedback":
            {},

        "turn_count":
            0,

        "turn_ceiling":
            turn_ceiling,

        "planner_attempts":
            0
    }


    # I am keeping my own copy of the latest state
    # because graph.stream() returns updates node by node.
    final_state = dict(
        initial_state
    )


    start_time = time.perf_counter()


    for event in graph.stream(
        initial_state
    ):

        for node_update in event.values():

            if isinstance(
                node_update,
                dict
            ):

                final_state.update(
                    node_update
                )


    latency_ms = (
        time.perf_counter()
        - start_time
    ) * 1000


    proposal = final_state.get(
        "planner_proposal",
        {}
    )

    feedback = final_state.get(
        "reviewer_feedback",
        {}
    )

    planner_attempts = final_state.get(
        "planner_attempts",
        0
    )


    # -----------------------------------------------------
    # Final objective schema validation
    # -----------------------------------------------------

    schema_valid = False

    try:

        PlannerOutput.model_validate(
            proposal
        )

        schema_valid = True

    except Exception:

        schema_valid = False


    approved = (
        feedback.get(
            "approved",
            False
        )
        is True
    )

    completed = (
        schema_valid
        and approved
    )


    # -----------------------------------------------------
    # Classify the run
    # -----------------------------------------------------

    if completed:

        if planner_attempts == 1:

            outcome = (
                "valid_first_attempt"
            )

        elif planner_attempts == 2:

            outcome = (
                "valid_after_1_retry"
            )

        else:

            outcome = (
                "valid_after_2_plus_retries"
            )

    else:

        outcome = (
            "hit_turn_ceiling"
        )


    return {

        "outcome":
            outcome,

        "completed":
            completed,

        "schema_valid":
            schema_valid,

        "approved":
            approved,

        "planner_attempts":
            planner_attempts,

        "turn_count":
            final_state.get(
                "turn_count",
                0
            ),

        "latency_ms":
            round(
                latency_ms,
                2
            ),

        "proposal":
            proposal,

        "reviewer_feedback":
            feedback
    }


# ---------------------------------------------------------
# Save results
# ---------------------------------------------------------

def save_json(
    filename: str,
    data
):

    path = (
        RAW_DIR / filename
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2
        )


def save_csv(
    filename: str,
    rows
):

    path = (
        RAW_DIR / filename
    )

    fieldnames = [
        "run",
        "outcome",
        "completed",
        "schema_valid",
        "approved",
        "planner_attempts",
        "turn_count",
        "latency_ms"
    ]


    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for row in rows:

            writer.writerow({
                key: row[key]
                for key in fieldnames
            })


# ---------------------------------------------------------
# 30-run schema experiment
# ---------------------------------------------------------

def run_schema_experiment():

    case = load_frozen_input()

    results = []


    print(
        "\n===== 30-RUN SCHEMA EXPERIMENT ====="
    )


    for run_number in range(
        1,
        31
    ):

        print(
            f"\nSchema run {run_number}/30"
        )

        result = run_once(
            case,
            turn_ceiling=10
        )

        result["run"] = run_number

        results.append(
            result
        )


    save_json(
        "schema_runs.json",
        results
    )

    save_csv(
        "schema_runs.csv",
        results
    )


    return results


# ---------------------------------------------------------
# Turn ceiling comparison
# 20 runs with ceiling 2 and 20 runs with ceiling 10
# ---------------------------------------------------------

def run_ceiling_comparison():

    case = load_frozen_input()

    all_results = {}


    for ceiling in [2, 10]:

        print(
            f"\n===== CEILING {ceiling} EXPERIMENT ====="
        )

        results = []


        for run_number in range(
            1,
            21
        ):

            print(
                f"\nCeiling {ceiling}: run {run_number}/20"
            )

            result = run_once(
                case,
                turn_ceiling=ceiling
            )

            result["run"] = run_number
            result["turn_ceiling"] = ceiling

            results.append(
                result
            )


        all_results[str(ceiling)] = results


        save_json(
            f"ceiling_{ceiling}_runs.json",
            results
        )

        save_csv(
            f"ceiling_{ceiling}_runs.csv",
            results
        )


        # I am calculating the completion rate.
        completed_count = sum(
            1
            for result in results
            if result["completed"]
        )

        completion_rate = (
            completed_count
            / len(results)
        ) * 100


        # I am calculating mean latency for this ceiling.
        mean_latency = sum(
            result["latency_ms"]
            for result in results
        ) / len(results)


        print(
            f"\nCeiling {ceiling} completion rate: "
            f"{completion_rate:.1f}%"
        )

        print(
            f"Ceiling {ceiling} mean latency: "
            f"{mean_latency:.2f} ms"
        )


    return all_results


#adding new func
def run_adversarial_experiment():
    """
    I am running one difficult input five times
    to see how often the graph reaches the ceiling.
    """

    path = (
        CASE_DIR / "adversarial_input.json"
    )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        case = json.load(file)

    results = []

    print(
        "\n===== ADVERSARIAL EXPERIMENT ====="
    )

    for run_number in range(
        1,
        6
    ):

        print(
            f"\nAdversarial run {run_number}/5"
        )

        result = run_once(
            case,
            turn_ceiling=1
        )

        result["run"] = run_number

        results.append(
            result
        )

    save_json(
        "adversarial_runs.json",
        results
    )

    save_csv(
        "adversarial_runs.csv",
        results
    )

    ceiling_hits = sum(
        result["outcome"] == "hit_turn_ceiling"
        for result in results
    )

    print(
        f"\nAdversarial ceiling hits: "
        f"{ceiling_hits}/5"
    )

    return results


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

#temporarily changing

if __name__ == "__main__":

    adversarial_results = (
        run_adversarial_experiment()
    )

    print(
        "\n===== ADVERSARIAL EXPERIMENT COMPLETE ====="
    )

# if __name__ == "__main__":

#     ceiling_results = (
#         run_ceiling_comparison()
#     )


#     print(
#         "\n===== CEILING COMPARISON COMPLETE ====="
#     )


#     print(
#         "\n===== SCHEMA EXPERIMENT COMPLETE ====="
#     )

#     print(
#         "Saved:"
#     )

#     print(
#         "reports/hw02/raw/schema_runs.json"
#     )

#     print(
#         "reports/hw02/raw/schema_runs.csv"
#     )