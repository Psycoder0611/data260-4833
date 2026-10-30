"""Planner agent: reads s4833_inbox (a question) and writes a plan to s4833_tasks.

Run:  python planner.py
"""

from typing import List, Optional

from hw8 import config
from hw8.agent_base import AgentRunner
from hw8.cli import build_parser, make_runner, run_forever
from hw8.pipeline import make_planner


def build_runner(argv: Optional[List[str]] = None) -> AgentRunner:
    """Parse arguments and build the Planner's runner."""
    parser = build_parser("Planner agent", config.PLANNER_GROUP)
    args = parser.parse_args(argv)
    return make_runner(
        args, "planner", config.INBOX_TOPIC, config.TASKS_TOPIC, make_planner
    )


if __name__ == "__main__":
    run_forever(build_runner())
