"""Run the Part 3 failure tests against the real Kafka and save the evidence.

Run:  python run_hw08_part3.py duplicate
      python run_hw08_part3.py death
      python run_hw08_part3.py poison
      python run_hw08_part3.py ordering
      python run_hw08_part3.py all

Needs the Kafka broker from docker-compose.hw8.yml. The Writers run as separate
processes with the stub model (no Ollama needed); every scenario runs the case
without the fix and the case with the fix. Results go to reports/hw08/raw/.
"""

import argparse
import asyncio
import time

from hw8 import config, failure_tests, kafka_io
from hw8.logs import run_logged


async def main_async(which: str, victim_ms: int, work_scale: float) -> None:
    """Run the chosen scenario(s) and save their JSON evidence."""
    found = await kafka_io.ensure_topics()
    print(f"topics ready (partitions): {found}", flush=True)
    if found.get(config.TASKS_TOPIC) != 2:
        raise SystemExit(f"{config.TASKS_TOPIC} must have 2 partitions: {found}")
    run_id = time.strftime("%m%d%H%M%S")
    launcher = failure_tests.SubprocessLauncher()
    state_dir = config.STATE_DIR
    raw = config.RAW_DIR
    names = ["duplicate", "death", "poison", "ordering"] if which == "all" else [which]
    for name in names:
        if name == "duplicate":
            result = await failure_tests.scenario_duplicate(launcher, run_id, state_dir)
        elif name == "death":
            result = await failure_tests.scenario_death(
                launcher, run_id, state_dir, victim_ms
            )
        elif name == "poison":
            result = await failure_tests.scenario_poison(launcher, run_id, state_dir)
        else:
            result = await failure_tests.scenario_ordering(
                launcher, run_id, state_dir, raw, work_scale
            )
        result["run_id"] = run_id
        result["verify_seed"] = config.VERIFY_SEED
        failure_tests.save_json(raw / f"part3_{name}.json", result)
        print(f"\nsaved reports/hw08/raw/part3_{name}.json", flush=True)


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description="HW8 Part 3 failure tests")
    parser.add_argument(
        "scenario", choices=["duplicate", "death", "poison", "ordering", "all"]
    )
    parser.add_argument("--victim-ms", type=int, default=8000)
    parser.add_argument("--work-scale", type=float, default=1.0)
    args = parser.parse_args()
    with run_logged(f"Part 3 {args.scenario}"):
        asyncio.run(main_async(args.scenario, args.victim_ms, args.work_scale))


if __name__ == "__main__":
    main()
