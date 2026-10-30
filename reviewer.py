"""Reviewer agent: reads s4833_drafts and writes an approval to s4833_final.

Run:  python reviewer.py
"""

from typing import List, Optional

from hw8 import config
from hw8.agent_base import AgentRunner
from hw8.cli import build_parser, make_runner, run_forever
from hw8.pipeline import make_reviewer


def build_runner(argv: Optional[List[str]] = None) -> AgentRunner:
    """Parse arguments and build the Reviewer's runner."""
    parser = build_parser("Reviewer agent", config.REVIEWER_GROUP)
    args = parser.parse_args(argv)
    return make_runner(
        args, "reviewer", config.DRAFTS_TOPIC, config.FINAL_TOPIC, make_reviewer
    )


if __name__ == "__main__":
    run_forever(build_runner())
