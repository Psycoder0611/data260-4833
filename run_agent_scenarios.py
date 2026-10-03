from agent_runner import run_agent


SCENARIOS = [
    {
        "name": "Search trial",
        "prompt": "Find clinical trials related to Cardio."
    },
    {
        "name": "Trial details",
        "prompt": "Give me details for clinical trial ID 5006."
    },
    {
        "name": "Organization summary",
        "prompt": "Summarize the clinical trials for organization ID 2."
    },
    {
        "name": "Safety rule scenario",
        "prompt": "Search all clinical trials using *."
    },
]


def main():
    print("=" * 70)
    print("HW5 LOCAL OLLAMA AGENT SCENARIOS")
    print("=" * 70)

    for index, scenario in enumerate(
        SCENARIOS,
        start=1
    ):
        print()
        print("-" * 70)
        print(
            f"SCENARIO {index}: "
            f"{scenario['name']}"
        )
        print("-" * 70)

        print(
            f"Prompt: {scenario['prompt']}"
        )

        result = run_agent(
            scenario["prompt"]
        )

        print(
            f"Steps: {result['steps']}"
        )

        print(
            f"Tool calls: "
            f"{result['tool_calls']}"
        )

        print(
            f"Stop reason: "
            f"{result['stop_reason']}"
        )

        print(
            f"Answer: {result['answer']}"
        )


if __name__ == "__main__":
    main()