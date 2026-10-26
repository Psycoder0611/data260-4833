"""HW7 Part 4 command line.

python -u run_hw07_part4.py schemas
python -u run_hw07_part4.py run --csv data/bike_scenarios/scenario_a_membership.csv
"""

import argparse
import json

from hw7 import bike_run, bike_tools
from hw7.config import RAW_DIR

URL = "https://lyftbikes.com/pricing"


def show(event: dict) -> None:
    if event["kind"] == "tool":
        flag = "ok " if event["success"] else "ERR"
        print(
            f"  step {event['step']}: {event['tool']:<17} {flag} "
            f"{event['tool_ms']:.0f} ms"
        )
    elif event["kind"] == "repair":
        print(f"  step {event['step']}: reply rejected - {event['message']}")
    elif event["kind"] == "final":
        print(f"  step {event['step']}: final answer")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schemas")
    run = sub.add_parser("run")
    run.add_argument("--csv", required=True)
    run.add_argument("--rider", default="R001")
    run.add_argument("--url", default=URL)
    args = ap.parse_args()

    if args.cmd == "schemas":
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        out = RAW_DIR / "bike_tool_schemas.json"
        out.write_text(json.dumps(bike_tools.tool_schemas(), indent=2) + "\n")
        print(f"wrote {out}")
        return

    print(f"=== HW7 Part 4: {args.csv} rider {args.rider} ===")
    r = bike_run.run_scenario(args.csv, args.rider, args.url, on_event=show)
    print(f"decision:   {r['decision']}")
    print(
        f"pay-per-use {r.get('pay_per_use_total')}  "
        f"membership {r.get('membership_total')}"
    )
    print(f"steps {r['steps']}  time {r['total_seconds']}s  stop {r['stop_reason']}")
    print(f"checks: {r['checks']}")


if __name__ == "__main__":
    main()
