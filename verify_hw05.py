import json
import subprocess
import sys
import time
from pathlib import Path

import requests


# ---------------------------------------------------------
# PERSONAL CONFIGURATION
# ---------------------------------------------------------

HOMEWORK = 5
SID4 = 4833
PORT_BASE = 8333
PREFIX = "s4833"
SEED = 4833
VERIFY_SEED = 264833

MODEL = "qwen3:8b"
EMBEDDING_MODEL = "nomic-embed-text"

OUTPUT_PATH = Path(
    "reports/hw05/verification.json"
)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def get_commit_hash():
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def add_check(
    checks,
    name,
    passed,
    details
):
    checks.append(
        {
            "name": name,
            "passed": passed,
            "details": details,
        }
    )


# ---------------------------------------------------------
# CHECK 1
# FastAPI backend
# ---------------------------------------------------------

def check_fastapi(checks):
    try:
        response = requests.get(
            f"http://127.0.0.1:{PORT_BASE}/docs",
            timeout=5,
        )

        passed = (
            response.status_code == 200
        )

        add_check(
            checks,
            "FastAPI backend responds on PORT_BASE",
            passed,
            (
                f"GET /docs returned "
                f"HTTP {response.status_code}"
            ),
        )

    except Exception as exc:
        add_check(
            checks,
            "FastAPI backend responds on PORT_BASE",
            False,
            str(exc),
        )


# ---------------------------------------------------------
# CHECK 2
# Meals MCP server file and import
# ---------------------------------------------------------

def check_meals_mcp(checks):
    try:
        import meals_server

        required_tools = [
            "search_meals_by_name",
            "meals_by_ingredient",
            "random_meal",
            "meal_details",
        ]

        missing = [
            tool
            for tool in required_tools
            if not hasattr(
                meals_server,
                tool
            )
        ]

        passed = len(missing) == 0

        details = (
            "All four required tools found"
            if passed
            else f"Missing tools: {missing}"
        )

        add_check(
            checks,
            "Meals MCP server imports and exposes required tools",
            passed,
            details,
        )

    except Exception as exc:
        add_check(
            checks,
            "Meals MCP server imports and exposes required tools",
            False,
            str(exc),
        )


# ---------------------------------------------------------
# CHECK 3
# Domain MCP server file and import
# ---------------------------------------------------------

def check_domain_mcp(checks):
    try:
        import domain_mcp_server

        required_tools = [
            "search_trials",
            "get_trial_details",
            "organization_trial_summary",
        ]

        missing = [
            tool
            for tool in required_tools
            if not hasattr(
                domain_mcp_server,
                tool
            )
        ]

        passed = len(missing) == 0

        details = (
            "All three required domain tools found"
            if passed
            else f"Missing tools: {missing}"
        )

        add_check(
            checks,
            "Domain MCP server imports and exposes required tools",
            passed,
            details,
        )

    except Exception as exc:
        add_check(
            checks,
            "Domain MCP server imports and exposes required tools",
            False,
            str(exc),
        )


# ---------------------------------------------------------
# CHECK 4
# Offline tool tests
# ---------------------------------------------------------

def check_offline_tests(checks):
    try:
        result = subprocess.run(
            [
                sys.executable,
                "test_tool_executor.py",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        passed = (
            result.returncode == 0
            and
            "FINAL SUMMARY: 8/8 tests passed"
            in result.stdout
        )

        add_check(
            checks,
            "Offline tool and agent tests",
            passed,
            (
                "8/8 tests passed"
                if passed
                else result.stdout[-500:]
            ),
        )

    except Exception as exc:
        add_check(
            checks,
            "Offline tool and agent tests",
            False,
            str(exc),
        )


# ---------------------------------------------------------
# CHECK 5
# Required raw artifacts
# ---------------------------------------------------------

def check_raw_artifacts(checks):
    required_files = [
        Path(
            "reports/hw05/raw/"
            "fault_injection_calls.csv"
        ),
        Path(
            "reports/hw05/raw/"
            "fault_metrics.json"
        ),
        Path(
            "reports/hw05/raw/"
            "agent_runs.jsonl"
        ),
        Path(
            "reports/hw05/raw/"
            "meals_mcp_inspector.json"
        ),
        Path(
            "reports/hw05/raw/"
            "domain_mcp_inspector.json"
        ),
    ]

    missing = [
        str(path)
        for path in required_files
        if not path.exists()
    ]

    passed = len(missing) == 0

    add_check(
        checks,
        "Required HW5 raw artifacts exist",
        passed,
        (
            "All required raw artifacts found"
            if passed
            else f"Missing: {missing}"
        ),
    )


# ---------------------------------------------------------
# CHECK 6
# Fault injection call count
# ---------------------------------------------------------

def check_fault_records(checks):
    import csv

    path = Path(
        "reports/hw05/raw/"
        "fault_injection_calls.csv"
    )

    try:
        with path.open(
            encoding="utf-8"
        ) as file:
            rows = list(
                csv.DictReader(file)
            )

        passed = len(rows) == 150

        add_check(
            checks,
            "150 fault-injection records exist",
            passed,
            f"Found {len(rows)} records",
        )

    except Exception as exc:
        add_check(
            checks,
            "150 fault-injection records exist",
            False,
            str(exc),
        )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    checks = []

    check_fastapi(checks)
    check_meals_mcp(checks)
    check_domain_mcp(checks)
    check_offline_tests(checks)
    check_raw_artifacts(checks)
    check_fault_records(checks)

    overall_pass = all(
        check["passed"]
        for check in checks
    )

    verification = {
        "homework": HOMEWORK,
        "sid4": SID4,
        "port_base": PORT_BASE,
        "prefix": PREFIX,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "model": MODEL,
        "embedding_model":
            EMBEDDING_MODEL,
        "commit_hash":
            get_commit_hash(),
        "overall_pass":
            overall_pass,
        "checks": checks,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            verification,
            file,
            indent=2
        )

    print(
        json.dumps(
            verification,
            indent=2
        )
    )

    print()
    print(
        f"verification.json written to "
        f"{OUTPUT_PATH}"
    )

    if not overall_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()