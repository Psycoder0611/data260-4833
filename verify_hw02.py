import json
import subprocess
import time
import urllib.request
from pathlib import Path

from agent_graph import PlannerOutput
from run_hw02_experiments import run_once


# ---------------------------------------------------------
# HW2 configuration
# ---------------------------------------------------------

HOMEWORK = 2
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833
DOMAIN_ID = 1

MODEL_NAME = "qwen3:8b"

OUTPUT_PATH = Path(
    "reports/hw02/verification.json"
)

CASE_PATH = Path(
    "reports/hw02/cases/schema_input.json"
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_commit_hash():
    """
    I am recording the exact Git commit being verified.
    """

    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "HEAD"
        ],
        capture_output=True,
        text=True,
        check=True
    )

    return result.stdout.strip()


def add_check(
    checks,
    name,
    passed,
    details
):
    """
    I am storing every smoke-test result
    in the same machine-readable format.
    """

    checks.append({
        "check": name,
        "passed": bool(passed),
        "details": details
    })


# ---------------------------------------------------------
# FastAPI smoke test
# ---------------------------------------------------------

def test_fastapi(checks):
    """
    I am starting the FastAPI application on PORT_BASE
    and checking that the home page and API respond.
    """

    process = subprocess.Popen(
        [
            "python",
            "main.py"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:

        # I am allowing the local server a few seconds to start.
        time.sleep(3)

        # Check the home page.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT_BASE}/",
            timeout=10
        ) as response:

            home_ok = (
                response.status == 200
            )

        add_check(
            checks,
            "FastAPI home responds on PORT_BASE",
            home_ok,
            f"GET / returned HTTP 200 on port {PORT_BASE}"
        )


        # Check the clinical-trial API.
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT_BASE}/api/trials",
            timeout=10
        ) as response:

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

            api_ok = (
                response.status == 200
                and isinstance(data, list)
            )

        add_check(
            checks,
            "Clinical trial API returns a list",
            api_ok,
            (
                f"GET /api/trials returned "
                f"{len(data)} record(s)"
            )
        )


    except Exception as error:

        add_check(
            checks,
            "FastAPI smoke test",
            False,
            str(error)
        )


    finally:

        process.terminate()

        try:

            process.wait(
                timeout=5
            )

        except subprocess.TimeoutExpired:

            process.kill()


# ---------------------------------------------------------
# Static frontend checks
# ---------------------------------------------------------

def test_frontend(checks):

    html = Path(
        "index.html"
    ).read_text(
        encoding="utf-8"
    )


    mobile_ok = (
        "@media (max-width: 375px)"
        in html
    )

    add_check(
        checks,
        "375px responsive CSS exists",
        mobile_ok,
        "index.html contains the required 375px media query"
    )


    states_ok = all(
        state_id in html
        for state_id in [
            'id="loadingState"',
            'id="emptyState"',
            'id="errorState"'
        ]
    )

    add_check(
        checks,
        "Loading, empty, and error states exist",
        states_ok,
        "Checked required state elements in index.html"
    )


# ---------------------------------------------------------
# Pydantic smoke test
# ---------------------------------------------------------

def test_schema(checks):

    try:

        result = PlannerOutput(
            tags=[
                "Sepsis Detection",
                "Machine Learning",
                "Patient Risk"
            ],
            summary=(
                "Machine learning helps identify "
                "patients at risk of sepsis."
            )
        )

        passed = (
            len(result.tags) == 3
        )

        add_check(
            checks,
            "PlannerOutput accepts valid schema",
            passed,
            "Valid output contains exactly three tags"
        )


    except Exception as error:

        add_check(
            checks,
            "PlannerOutput accepts valid schema",
            False,
            str(error)
        )


    try:

        PlannerOutput(
            tags=[
                "AI",
                "ML"
            ],
            summary="Short summary."
        )

        invalid_rejected = False

    except Exception:

        invalid_rejected = True


    add_check(
        checks,
        "PlannerOutput rejects invalid schema",
        invalid_rejected,
        "Invalid short/two-tag output must fail validation"
    )


# ---------------------------------------------------------
# LangGraph smoke test
# ---------------------------------------------------------

def test_langgraph(checks):

    try:

        case = json.loads(
            CASE_PATH.read_text(
                encoding="utf-8"
            )
        )


        # I am using a small ceiling for the smoke test.
        # This checks that the graph actually terminates.
        result = run_once(
            case,
            turn_ceiling=2
        )


        finished = (
            result["planner_attempts"] <= 2
        )

        add_check(
            checks,
            "LangGraph terminates within configured ceiling",
            finished,
            (
                f"Planner attempts: "
                f"{result['planner_attempts']}"
            )
        )


        schema_ok = (
            result["schema_valid"]
        )

        add_check(
            checks,
            "LangGraph final Planner output passes schema",
            schema_ok,
            (
                f"Schema valid: "
                f"{result['schema_valid']}"
            )
        )


    except Exception as error:

        add_check(
            checks,
            "LangGraph smoke test",
            False,
            str(error)
        )


# ---------------------------------------------------------
# Main verification
# ---------------------------------------------------------

def main():

    checks = []

    commit_hash = (
        get_commit_hash()
    )


    test_frontend(
        checks
    )

    test_fastapi(
        checks
    )

    test_schema(
        checks
    )

    test_langgraph(
        checks
    )


    all_passed = all(
        check["passed"]
        for check in checks
    )


    verification = {

        "homework": HOMEWORK,

        "sid4": SID4,

        "commit_hash": commit_hash,

        "configuration": {
            "port_base": PORT_BASE,
            "prefix": PREFIX,
            "domain_id": DOMAIN_ID,
            "model": MODEL_NAME
        },

        "seed": SEED,

        "verify_seed": VERIFY_SEED,

        "checks": checks,

        "overall_passed": all_passed
    }


    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    OUTPUT_PATH.write_text(
        json.dumps(
            verification,
            indent=2
        ),
        encoding="utf-8"
    )


    print(
        json.dumps(
            verification,
            indent=2
        )
    )


    print(
        f"\nSaved verification to: "
        f"{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()