"""Command-line helpers shared by planner.py, writer.py and reviewer.py."""

import argparse
import asyncio
import signal
import sys
from typing import Callable, Optional

from hw8 import config
from hw8.agent_base import AgentOptions, AgentRunner, RetriesExhausted
from hw8.logs import get_logger
from hw8.pipeline import Brain


def build_parser(description: str, default_group: str) -> argparse.ArgumentParser:
    """Create an argument parser with the options every agent accepts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--instance", default="", help="label such as A or B")
    parser.add_argument("--group", default=default_group, help="consumer group id")
    parser.add_argument(
        "--offset-reset",
        choices=["earliest", "latest"],
        default="earliest",
        help="where a group with no committed offset starts",
    )
    parser.add_argument(
        "--commit-mode",
        choices=["after", "on_receive"],
        default="after",
        help="after = commit once the result is published (fix); "
        "on_receive = commit before processing (the broken 'before' behaviour)",
    )
    parser.add_argument(
        "--no-idempotency", action="store_true", help="turn duplicate detection off"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=config.MAX_ATTEMPTS,
        help="attempts per message; 0 = retry forever (the 'before' behaviour)",
    )
    parser.add_argument(
        "--no-dead-letter",
        action="store_true",
        help="stop with an error instead of sending to the dead-letter topic",
    )
    parser.add_argument(
        "--key-by",
        choices=["correlation", "entity", "none"],
        default="correlation",
        help="Kafka key of the messages this agent publishes",
    )
    parser.add_argument(
        "--llm",
        choices=["ollama", "stub"],
        default=config.LLM_MODE,
        help="ollama = qwen3:8b; stub = fixed text (failure tests only)",
    )
    parser.add_argument(
        "--work-seconds",
        type=float,
        default=0.0,
        help="stub mode only: fixed delay per message",
    )
    parser.add_argument("--state-db", default=None, help="idempotency SQLite file")
    parser.add_argument("--bootstrap", default=None, help="Kafka bootstrap servers")
    return parser


def options_from_args(
    args: argparse.Namespace,
    name: str,
    in_topic: str,
    out_topic: Optional[str],
) -> AgentOptions:
    """Turn parsed arguments into AgentOptions."""
    return AgentOptions(
        name=name,
        in_topic=in_topic,
        out_topic=out_topic,
        group_id=args.group,
        instance=args.instance,
        commit_mode=args.commit_mode,
        idempotent=not args.no_idempotency,
        max_attempts=args.max_attempts,
        dead_letter=not args.no_dead_letter,
        key_mode=args.key_by,
        offset_reset=args.offset_reset,
        bootstrap=args.bootstrap,
        store_path=args.state_db,
    )


def make_brain(args: argparse.Namespace) -> Brain:
    """Build the Brain (real model or stub) from the arguments."""
    return Brain(args.llm, args.work_seconds)


def run_forever(runner: AgentRunner) -> None:
    """Run an agent until Ctrl+C / SIGTERM; leave the group cleanly on exit."""

    async def main() -> None:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, task.cancel)  # type: ignore[union-attr]
            except NotImplementedError:  # pragma: no cover (Windows)
                pass
        try:
            await runner.run()
        except asyncio.CancelledError:
            runner.log.info("stopped (processed %d messages)", runner.processed)

    try:
        asyncio.run(main())
    except RetriesExhausted as exc:
        get_logger(runner.label).info("FATAL %s - stopping without a commit", exc)
        sys.exit(2)


def make_runner(
    args: argparse.Namespace,
    name: str,
    in_topic: str,
    out_topic: Optional[str],
    handler_factory: Callable,
) -> AgentRunner:
    """Create the AgentRunner for one agent from parsed arguments."""
    options = options_from_args(args, name, in_topic, out_topic)
    return AgentRunner(options, handler_factory(make_brain(args)))
