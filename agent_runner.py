import json
from datetime import datetime
from pathlib import Path

import requests

from tool_executor import execute_tool


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

MODEL_NAME = "qwen3:8b"

OLLAMA_URL = (
    "http://localhost:11434/api/chat"
)

MAX_STEPS = 5

LOG_PATH = Path(
    "reports/hw05/raw/agent_runs.jsonl"
)

LOG_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------

def write_log(record):
    with LOG_PATH.open(
        "a",
        encoding="utf-8"
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False
            )
            + "\n"
        )


# ---------------------------------------------------------
# OLLAMA MODEL WRAPPER
# ---------------------------------------------------------

class OllamaModel:
    def __init__(
        self,
        model_name=MODEL_NAME
    ):
        self.model_name = model_name

    def generate(self, messages):
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": self.model_name,
                "messages": messages,
                "stream": False,
                "format": "json",
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        return data[
            "message"
        ]["content"]


# ---------------------------------------------------------
# AGENT INSTRUCTIONS
# ---------------------------------------------------------

SYSTEM_PROMPT = """
You are a Clinical Trial Listings agent.

You have exactly three tools:

1. search_trials
   inputs:
   {"query": string, "limit": integer}

2. get_trial_details
   inputs:
   {"trial_id": positive integer}

3. organization_trial_summary
   inputs:
   {"organization_id": positive integer}

At every step, return ONLY valid JSON.

To call a tool:
{
  "action": "tool",
  "tool": "search_trials",
  "inputs": {
    "query": "Cardio",
    "limit": 10
  }
}

To finish:
{
  "action": "final",
  "answer": "your answer"
}

Use tool results when needed.
Never invent trial data.
Do not use unrestricted wildcard searches.
"""


# ---------------------------------------------------------
# AGENT LOOP
# ---------------------------------------------------------

def run_agent(
    user_input,
    model=None,
    max_steps=MAX_STEPS,
    tool_executor=execute_tool,
):
    if model is None:
        model = OllamaModel()

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_input,
        },
    ]

    tool_call_count = 0

    for step in range(
        1,
        max_steps + 1
    ):
        try:
            raw_response = model.generate(
                messages
            )

            decision = json.loads(
                raw_response
            )

        except Exception as exc:
            stop_reason = "model_error"

            write_log(
                {
                    "timestamp":
                        datetime.now().isoformat(),
                    "user_input":
                        user_input,
                    "step":
                        step,
                    "tool":
                        None,
                    "inputs":
                        None,
                    "result":
                        None,
                    "final":
                        None,
                    "stop_reason":
                        stop_reason,
                    "error":
                        str(exc),
                }
            )

            return {
                "answer": None,
                "steps": step,
                "tool_calls":
                    tool_call_count,
                "stop_reason":
                    stop_reason,
            }

        if decision.get("action") == "final":
            answer = decision.get(
                "answer",
                ""
            )

            stop_reason = (
                "normal_completion"
            )

            write_log(
                {
                    "timestamp":
                        datetime.now().isoformat(),
                    "user_input":
                        user_input,
                    "step":
                        step,
                    "tool":
                        None,
                    "inputs":
                        None,
                    "result":
                        None,
                    "final":
                        answer,
                    "stop_reason":
                        stop_reason,
                }
            )

            return {
                "answer": answer,
                "steps": step,
                "tool_calls":
                    tool_call_count,
                "stop_reason":
                    stop_reason,
            }

        if decision.get("action") != "tool":
            continue

        tool_name = decision.get(
            "tool"
        )

        tool_inputs = decision.get(
            "inputs",
            {}
        )

        tool_result = tool_executor(
            tool_name,
            tool_inputs
        )

        tool_call_count += 1

        parsed_result = json.loads(
            tool_result
        )

        write_log(
            {
                "timestamp":
                    datetime.now().isoformat(),
                "user_input":
                    user_input,
                "step":
                    step,
                "tool":
                    tool_name,
                "inputs":
                    tool_inputs,
                "result":
                    parsed_result,
                "final":
                    None,
                "stop_reason":
                    None,
            }
        )

        if (
            parsed_result["ok"]
            is False
            and str(
                parsed_result["error"]
            ).startswith(
                "Safety rule:"
            )
        ):
            stop_reason = (
                "safety_rule_block"
            )

            write_log(
                {
                    "timestamp":
                        datetime.now().isoformat(),
                    "user_input":
                        user_input,
                    "step":
                        step,
                    "tool":
                        tool_name,
                    "inputs":
                        tool_inputs,
                    "result":
                        parsed_result,
                    "final":
                        None,
                    "stop_reason":
                        stop_reason,
                }
            )

            return {
                "answer":
                    parsed_result[
                        "error"
                    ],
                "steps": step,
                "tool_calls":
                    tool_call_count,
                "stop_reason":
                    stop_reason,
            }

        messages.append(
            {
                "role": "assistant",
                "content":
                    raw_response,
            }
        )

        messages.append(
            {
                "role": "user",
                "content":
                    "Tool result:\n"
                    + tool_result
                    + "\nContinue.",
            }
        )

    stop_reason = "max_steps"

    write_log(
        {
            "timestamp":
                datetime.now().isoformat(),
            "user_input":
                user_input,
            "step":
                max_steps,
            "tool":
                None,
            "inputs":
                None,
            "result":
                None,
            "final":
                None,
            "stop_reason":
                stop_reason,
        }
    )

    return {
        "answer": None,
        "steps": max_steps,
        "tool_calls":
            tool_call_count,
        "stop_reason":
            stop_reason,
    }