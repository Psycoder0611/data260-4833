import json

from tool_executor import execute_tool
import tempfile
from pathlib import Path

import agent_runner
from agent_runner import run_agent

# ---------------------------------------------------------
# OFFLINE MOCK TOOL REGISTRY
# No database, API, LLM, or network is used.
# ---------------------------------------------------------

def mock_search_trials(inputs):
    query = str(
        inputs.get("query", "")
    ).strip()

    if not query:
        return {
            "ok": False,
            "data": None,
            "error": "query must not be empty",
        }

    return {
        "ok": True,
        "data": [
            {
                "id": 101,
                "trialTitle":
                    "Mock Cardiovascular Study",
                "trial_code":
                    "MOCK-001",
            }
        ],
        "error": None,
    }


def mock_get_trial_details(inputs):
    trial_id = inputs.get("trial_id")

    if (
        not isinstance(trial_id, int)
        or trial_id < 1
    ):
        return {
            "ok": False,
            "data": None,
            "error":
                "trial_id must be a positive integer",
        }

    return {
        "ok": True,
        "data": {
            "id": trial_id,
            "trialTitle":
                "Mock Clinical Trial",
        },
        "error": None,
    }


def mock_organization_summary(inputs):
    organization_id = inputs.get(
        "organization_id"
    )

    if (
        not isinstance(organization_id, int)
        or organization_id < 1
    ):
        return {
            "ok": False,
            "data": None,
            "error":
                "organization_id must be a positive integer",
        }

    return {
        "ok": True,
        "data": {
            "organization_id":
                organization_id,
            "trial_count": 2,
            "total_participant_capacity":
                300,
        },
        "error": None,
    }


MOCK_REGISTRY = {
    "search_trials":
        mock_search_trials,

    "get_trial_details":
        mock_get_trial_details,

    "organization_trial_summary":
        mock_organization_summary,
}


# ---------------------------------------------------------
# SIMPLE ASSERT TEST RUNNER
# ---------------------------------------------------------

passed = 0
total = 0


def run_test(name, test_function):
    global passed, total

    total += 1

    try:
        test_function()

        print(
            f"PASS - {name}"
        )

        passed += 1

    except AssertionError as exc:
        print(
            f"FAIL - {name}: {exc}"
        )


# ---------------------------------------------------------
# TEST 1
# search_trials valid
# ---------------------------------------------------------

def test_search_valid():
    result = json.loads(
        execute_tool(
            "search_trials",
            {
                "query": "Cardio",
                "limit": 10,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert len(result["data"]) == 1


# ---------------------------------------------------------
# TEST 2
# search_trials invalid
# Reuses Part 3 rejected input
# ---------------------------------------------------------

def test_search_invalid():
    result = json.loads(
        execute_tool(
            "search_trials",
            {
                "query": " ",
                "limit": 10,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert (
        result["error"]
        == "query must not be empty"
    )


# ---------------------------------------------------------
# TEST 3
# get_trial_details valid
# ---------------------------------------------------------

def test_details_valid():
    result = json.loads(
        execute_tool(
            "get_trial_details",
            {
                "trial_id": 101,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is True
    assert (
        result["data"]["id"]
        == 101
    )


# ---------------------------------------------------------
# TEST 4
# get_trial_details invalid
# Reuses Part 3 rejected input
# ---------------------------------------------------------

def test_details_invalid():
    result = json.loads(
        execute_tool(
            "get_trial_details",
            {
                "trial_id": 0,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is False
    assert (
        result["error"]
        ==
        "trial_id must be a positive integer"
    )


# ---------------------------------------------------------
# TEST 5
# organization_trial_summary valid
# ---------------------------------------------------------

def test_summary_valid():
    result = json.loads(
        execute_tool(
            "organization_trial_summary",
            {
                "organization_id": 2,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is True
    assert (
        result["data"]["organization_id"]
        == 2
    )


# ---------------------------------------------------------
# TEST 6
# organization_trial_summary invalid
# Reuses Part 3 rejected input
# ---------------------------------------------------------

def test_summary_invalid():
    result = json.loads(
        execute_tool(
            "organization_trial_summary",
            {
                "organization_id": 0,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is False
    assert (
        result["error"]
        ==
        "organization_id must be a positive integer"
    )


# ---------------------------------------------------------
# RUN TESTS
# ---------------------------------------------------------

run_test(
    "search_trials valid input",
    test_search_valid
)

run_test(
    "search_trials rejected input",
    test_search_invalid
)

run_test(
    "get_trial_details valid input",
    test_details_valid
)

run_test(
    "get_trial_details rejected input",
    test_details_invalid
)

run_test(
    "organization_trial_summary valid input",
    test_summary_valid
)

run_test(
    "organization_trial_summary rejected input",
    test_summary_invalid
)

# ---------------------------------------------------------
# TEST 7
# Safety rule blocks unrestricted wildcard search
# ---------------------------------------------------------

def test_safety_rule_block():
    result = json.loads(
        execute_tool(
            "search_trials",
            {
                "query": "*",
                "limit": 10,
            },
            MOCK_REGISTRY,
        )
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert (
        result["error"]
        ==
        "Safety rule: unrestricted wildcard "
        "trial searches are not allowed"
    )


# ---------------------------------------------------------
# MOCK MODEL FOR MAX_STEPS TEST
# ---------------------------------------------------------

class MockModel:
    """
    Always asks for another valid tool call.
    This forces the agent loop to reach max_steps.
    """

    def generate(self, messages):
        return json.dumps(
            {
                "action": "tool",
                "tool": "search_trials",
                "inputs": {
                    "query": "Cardio",
                    "limit": 10,
                },
            }
        )


def mock_agent_tool_executor(
    name,
    inputs
):
    """
    Offline tool executor for the agent test.
    No database or external service is used.
    """

    return json.dumps(
        {
            "ok": True,
            "data": [
                {
                    "id": 101,
                    "trialTitle":
                        "Mock Cardiovascular Study",
                }
            ],
            "error": None,
        }
    )


# ---------------------------------------------------------
# TEST 8
# Agent stops at max_steps
# ---------------------------------------------------------

def test_agent_max_steps():
    original_log_path = (
        agent_runner.LOG_PATH
    )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:

            agent_runner.LOG_PATH = (
                Path(temp_dir)
                / "agent_runs.jsonl"
            )

            result = run_agent(
                "Keep searching for trials",
                model=MockModel(),
                max_steps=3,
                tool_executor=
                    mock_agent_tool_executor,
            )

            assert (
                result["stop_reason"]
                == "max_steps"
            )

            assert result["steps"] == 3

            assert (
                result["tool_calls"]
                == 3
            )

            assert (
                agent_runner.LOG_PATH.exists()
            )

    finally:
        agent_runner.LOG_PATH = (
            original_log_path
        )


# ---------------------------------------------------------
# RUN ADDITIONAL TESTS
# ---------------------------------------------------------

run_test(
    "execute_tool safety rule blocked",
    test_safety_rule_block
)

run_test(
    "run_agent stops at max_steps",
    test_agent_max_steps
)


# ---------------------------------------------------------
# FINAL SUMMARY
# ---------------------------------------------------------

print()
print("=" * 55)
print(
    f"FINAL SUMMARY: "
    f"{passed}/{total} tests passed"
)
print("=" * 55)


assert passed == total