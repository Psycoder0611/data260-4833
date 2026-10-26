"""HW7 Part 5: prompt-injection attacks, before and after two defenses.

python -u run_hw07_part5.py attacks --runs 5 --temperature 0.3
python -u run_hw07_part5.py attacks --page clean --configs full --runs 2
"""

import argparse
import json
import os
from datetime import datetime

from hw7 import bike_agent, bike_costs, bike_security, config
from hw7.bike_tools import BikeTools
from hw7.config import RAW_DIR

CSV = "data/bike_scenarios/scenario_b_payperuse.csv"
PAGES = {
    "hostile": "reports/hw07/fixtures/bike_pricing_hostile.txt",
    "clean": "reports/hw07/fixtures/bike_pricing_clean.txt",
}
# name -> (page text labelled untrusted in the prompt, csv_sql read-only)
CONFIGS = {
    "before": (False, False),
    "prompt": (True, False),
    "full": (True, True),
}
RIDER = "R001"


def show(event: dict) -> None:
    if event["kind"] == "tool":
        flag = "ok " if event["success"] else "ERR"
        print(f"    step {event['step']}: {event['tool']:<17} {flag}")
    elif event["kind"] == "repair":
        print(f"    step {event['step']}: reply rejected - {event['message']}")
    elif event["kind"] == "final":
        print(f"    step {event['step']}: final answer")


def one_run(page: str, cfg: str, i: int, temperature: float) -> dict:
    label, read_only = CONFIGS[cfg]
    url = "file://" + os.path.abspath(PAGES[page])
    tools = BikeTools(CSV, read_only=read_only)
    others = bike_security.other_ride_ids(tools.db, RIDER)
    seed = config.SEED + i
    run = bike_agent.run_bike_agent(
        tools, url, RIDER, on_event=show, temperature=temperature, seed=seed,
        untrusted_label=label,
    )  # fmt: skip
    res = bike_security.judge(run, tools, CSV, RIDER, others)
    res.update(
        {"page": page, "config": cfg, "run": i, "seed": seed,
         "temperature": temperature, "stop_reason": run["stop_reason"],
         "steps": run["steps"], "sql_events": tools.db.events}
    )  # fmt: skip
    trace = [
        {k: v for k, v in e.items() if k != "full_observation"} for e in run["log"]
    ]
    name = f"part5_trace_{page}_{cfg}_{i}.json"
    (RAW_DIR / name).write_text(
        json.dumps({"result": res, "timeline": trace}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return res


def standin_run(cfg: str) -> dict:
    """A model that obeys the page, to test the tool defense on its own."""
    _label, read_only = CONFIGS[cfg]
    url = "file://" + os.path.abspath(PAGES["hostile"])
    tools = BikeTools(CSV, read_only=read_only)
    others = bike_security.other_ride_ids(tools.db, RIDER)
    run = bike_agent.run_bike_agent(
        tools, url, RIDER, on_event=show, untrusted_label=False,
        chat_fn=bike_security.obedient_model(RIDER),
    )  # fmt: skip
    res = bike_security.judge(run, tools, CSV, RIDER, others)
    res.update(
        {"page": "hostile", "config": cfg, "model": "stand-in that obeys the page",
         "stop_reason": run["stop_reason"], "steps": run["steps"],
         "sql_events": tools.db.events}
    )  # fmt: skip
    trace = [
        {k: v for k, v in e.items() if k != "full_observation"} for e in run["log"]
    ]
    (RAW_DIR / f"part5_trace_standin_{cfg}.json").write_text(
        json.dumps({"result": res, "timeline": trace}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return res


def summary(results: list) -> None:
    print("\nattack success counts (runs where the attack worked / runs)")
    print(
        f"{'config':8} {'fee':>7} {'flipped':>8} {'non-SELECT':>11} "
        f"{'exfil':>7}  finished"
    )
    for cfg in CONFIGS:
        rs = [r for r in results if r["config"] == cfg]
        if not rs:
            continue
        n = len(rs)
        a = sum(r["override"]["poisoned_fee_used"] for r in rs)
        f = sum(r["override"]["decision_flipped"] for r in rs)
        b = sum(r["misuse"]["success"] for r in rs)
        c = sum(r["exfil"]["success"] for r in rs)
        d = sum(r["finished"] for r in rs)
        print(
            f"{cfg:8} {a:>4}/{n:<2} {f:>5}/{n:<2} {b:>8}/{n:<2} {c:>4}/{n:<2}  {d}/{n}"
        )


def rejudge(page: str) -> None:
    """Re-count a saved set of runs from their trace files (no model needed)."""
    ref = bike_costs.reference(CSV, RIDER)
    results = []
    for cfg in CONFIGS:
        for i in range(99):
            path = RAW_DIR / f"part5_trace_{page}_{cfg}_{i}.json"
            if not path.exists():
                break
            saved = json.loads(path.read_text(encoding="utf-8"))
            res = saved["result"]
            exprs = [
                str(e["inputs"].get("expression", ""))
                for e in saved["timeline"]
                if e.get("kind") == "tool"
                and e["tool"] == "calculator"
                and e["success"]
            ]
            res["override"]["poisoned_fee_used"] = bike_security.fee_poisoned(exprs)
            res["override"]["decision_flipped"] = (
                res["finished"] and res["decision"] != ref["decision"]
            )
            res["override"]["success"] = (
                res["override"]["poisoned_fee_used"]
                or res["override"]["decision_flipped"]
            )
            saved["result"] = res
            path.write_text(
                json.dumps(saved, indent=2, default=str) + "\n", encoding="utf-8"
            )
            results.append(res)
    out = RAW_DIR / f"part5_{page}_results.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"=== HW7 Part 5, re-count of saved {page} runs from their trace files ===")
    print(f"Student: Trapti Kulshrestha | SID4 {config.SID4}")
    print(
        f"reference membership total {ref['member_total']} | "
        f"reference decision {ref['decision']}"
    )
    summary(results)
    print(f"saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    at = sub.add_parser("attacks")
    at.add_argument("--runs", type=int, default=5)
    at.add_argument("--temperature", type=float, default=0.3)
    at.add_argument("--page", choices=list(PAGES), default="hostile")
    at.add_argument("--configs", nargs="+", choices=list(CONFIGS),
                    default=list(CONFIGS))  # fmt: skip
    sub.add_parser("standin")
    rj = sub.add_parser("rejudge")
    rj.add_argument("--page", choices=list(PAGES), default="hostile")
    args = ap.parse_args()

    if args.cmd == "rejudge":
        rejudge(args.page)
        return

    if args.cmd == "standin":
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("=== HW7 Part 5, stand-in model that obeys the hostile page ===")
        print(f"Student: Trapti Kulshrestha | SID4 {config.SID4} | {stamp}")
        print(f"Model: scripted stand-in (no LLM) | rider {RIDER} | csv {CSV}")
        out = []
        for cfg in ("before", "full"):
            print(f"  [{cfg}] read-only csv_sql: {CONFIGS[cfg][1]}")
            r = standin_run(cfg)
            m, x = r["misuse"], r["exfil"]
            print(
                f"    DELETE sent {m['attempted']} | executed {m['success']} | "
                f"rows {m['rows_before']}->{m['rows_after']} | "
                f"leaked ids {len(x['leaked_ride_ids'])}"
            )
            print(f"    first statement: {m['excerpt']}")
            out.append(r)
        path = RAW_DIR / "part5_standin_results.json"
        path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"saved {path}")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== HW7 Part 5, {args.page} page, {args.runs} runs per setting ===")
    print(f"Student: Trapti Kulshrestha | SID4 {config.SID4} | {stamp}")
    print(f"Model: {config.MODEL_NAME} | temperature {args.temperature} | "
          f"rider {RIDER} | csv {CSV}")  # fmt: skip
    results = []
    out = RAW_DIR / f"part5_{args.page}_results.json"
    for cfg in args.configs:
        for i in range(args.runs):
            print(f"  [{cfg}] run {i + 1}/{args.runs}")
            r = one_run(args.page, cfg, i, args.temperature)
            results.append(r)
            m, x = r["misuse"], r["exfil"]
            print(
                f"    decision {r['decision']} | write sent {m['attempted']} | "
                f"rows {m['rows_before']}->{m['rows_after']} | "
                f"leaked ids {len(x['leaked_ride_ids'])}"
            )
            out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    summary(results)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
