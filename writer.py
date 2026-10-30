"""Writer agent: reads s4833_tasks (a plan) and writes a draft to s4833_drafts.

Run:  python writer.py
Several Writers can share the group (--instance A / --instance B); Kafka then
gives each one a share of the s4833_tasks partitions.
"""

from pathlib import Path
from typing import List, Optional

from hw8 import config
from hw8.agent_base import AgentRunner
from hw8.cli import build_parser, make_runner, run_forever
from hw8.pipeline import make_writer


def build_runner(argv: Optional[List[str]] = None) -> AgentRunner:
    """Parse arguments and build the Writer's runner."""
    parser = build_parser("Writer agent", config.WRITER_GROUP)
    parser.add_argument(
        "--record-path",
        default=None,
        help="append one line per finished message here (ordering test)",
    )
    args = parser.parse_args(argv)
    record_path = Path(args.record_path) if args.record_path else None

    def factory(brain):  # the brain is built from the same arguments
        return make_writer(brain, record_path)

    return make_runner(args, "writer", config.TASKS_TOPIC, config.DRAFTS_TOPIC, factory)


if __name__ == "__main__":
    run_forever(build_runner())
