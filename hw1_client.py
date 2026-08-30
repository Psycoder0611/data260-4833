import json
from pathlib import Path

from src.model_client import ModelClient


# Load system instructions from AGENT.md
AGENT_FILE = Path(__file__).resolve().parent / "AGENT.md"


def load_agent_instructions():
    """
    Read the system prompt from AGENT.md.
    """

    with open(
        AGENT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read().strip()


def serialized_history_length(history):
    """
    Return the serialized conversation-history length.

    /stats must show this value without changing the history.
    """

    serialized = json.dumps(
        history,
        ensure_ascii=False
    )

    return len(serialized)


def print_stats(client, history):
    """
    Display cumulative conversation statistics.
    This function does not modify conversation history.
    """

    stats = client.get_stats()

    print("\nConversation Stats")
    print(
        "Turn count:",
        stats["turn_count"]
    )

    print(
        "Cumulative input tokens:",
        stats["input_tokens"]
    )

    print(
        "Cumulative output tokens:",
        stats["output_tokens"]
    )

    print(
        "Cumulative total tokens:",
        stats["total_tokens"]
    )

    print(
        "Serialized conversation-history length:",
        serialized_history_length(history)
    )


def main():

    # Read the strict bullet-only code review instructions
    system_prompt = load_agent_instructions()

    # Initialize reusable model adapter
    client = ModelClient(
        model="qwen3:8b",
        temperature=0.0
    )

    # Conversation history starts with the system prompt
    history = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    print(
        "HW1 Model Client"
    )

    print(
        "Enter code-review requests."
    )

    print(
        "Commands: /stats, /exit"
    )

    while True:

        user_input = input(
            "\nYou: "
        ).strip()

        # Exit command
        if user_input.lower() in {
            "/exit",
            "exit",
            "quit"
        }:
            break

        # Show statistics without changing history
        if user_input.lower() == "/stats":

            print_stats(
                client,
                history
            )

            continue

        # Ignore empty input
        if not user_input:
            continue

        # Add user message to conversation history
        history.append({
            "role": "user",
            "content": user_input
        })

        try:

            # All model calls go through model_client.py
            response = client.complete(
                history
            )

        except Exception as error:

            print(
                f"\nModel error: {error}"
            )

            continue

        assistant_text = str(
            response["content"]
        )

        print(
            "\nAssistant:"
        )

        print(
            assistant_text
        )

        # Print token usage after every model response
        print(
            "\nToken Usage"
        )

        print(
            "Input tokens:",
            response["input_tokens"]
        )

        print(
            "Output tokens:",
            response["output_tokens"]
        )

        print(
            "Total tokens:",
            response["total_tokens"]
        )

        # Add assistant response to conversation history
        history.append({
            "role": "assistant",
            "content": assistant_text
        })

    # Print cumulative statistics when exiting
    print(
        "\nFinal Conversation Stats"
    )

    print_stats(
        client,
        history
    )


if __name__ == "__main__":
    main()