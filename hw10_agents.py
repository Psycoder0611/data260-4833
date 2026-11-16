"""Traced Planner / Writer / Reviewer for HW10 (the HW8 agents plus span logging).

Run each in its own terminal (after the HW8 Kafka stack is up):

    python hw10_agents.py planner
    python hw10_agents.py writer
    python hw10_agents.py reviewer

Same handlers, retries (3), idempotency and dead-letter rule as planner.py / writer.py /
reviewer.py of HW8; the only addition is that each stage and each queue wait writes a
span with trace_id = correlation_id to reports/hw10/raw/spans.jsonl.
Do not run these together with the HW8 agents (they would share the topics).
"""

import argparse

from hw8.cli import run_forever
from hw8.pipeline import Brain

from hw10 import config
from hw10.kafka_trace import build_runner
from hw10.logs import banner


def main() -> None:
    """Parse the role and run the traced agent until Ctrl+C."""
    parser = argparse.ArgumentParser(description="HW10 traced agent")
    parser.add_argument("role", choices=["planner", "writer", "reviewer"])
    parser.add_argument("--llm", choices=["ollama", "stub"], default="ollama")
    parser.add_argument("--bootstrap", default=None)
    args = parser.parse_args()
    print(banner(f"{args.role} (traced agent)"))
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    runner = build_runner(args.role, Brain(args.llm), bootstrap=args.bootstrap)
    run_forever(runner)


if __name__ == "__main__":
    main()
