"""HW7 Part 2 demo runner.

python run_hw07_part2.py tasks         # tasks A, B, C
python run_hw07_part2.py recover       # nonexistent ID error recovery
python run_hw07_part2.py reliability   # 21 attempts (7 per task)
"""

import argparse
import csv
import json
from datetime import datetime

from hw7 import agent, cases, config, reliability
from tool_executor import execute_tool

RAW = config.RAW_DIR


def banner(title: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Student: Trapti Kulshrestha | SID4 {config.SID4} | {title} | {stamp}")
    print(
        f"Model: {config.MODEL_NAME} | max iterations {config.MAX_ITERATIONS} | "
        f"max failed repairs {config.MAX_FAILED_REPAIRS}"
    )
    print("-" * 78)


def show_result(result: dict) -> None:
    for number, call in enumerate(result["tool_log"], start=1):
        status = "ok" if call["ok"] else f"error: {call['error']}"
        print(
            f"  tool call {number}: {call['tool']} "
            f"{json.dumps(call['inputs'])} -> {status}"
        )
    print(f"  repairs: {result['repair_attempts']} tried, {result['repair_ok']} worked")
    print(f"  stop reason: {result['stop_reason']}")
    print(f"  TOTAL TOOL CALLS: {result['tool_calls']}")
    print(f"  final answer: {result['answer']}")


def reset_log(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def cmd_tasks(_args) -> None:
    banner("HW7 Part 2: verification tasks")
    reset_log(config.TOOL_LOG_PATH)
    for case in cases.CASES:
        print(f"Task {case['id']}: {case['prompt']}")
        result = agent.run_agent(case["prompt"], run_id=f"task-{case['id']}")
        show_result(result)
        verdict = "PASS" if cases.chain_ok(case, result["tool_log"]) else "FAIL"
        print(f"  chain check (needs 2+ tool calls, no follow-up prompt): {verdict}")
        print("-" * 78)


def cmd_recover(_args) -> None:
    banner("HW7 Part 2: error recovery")
    print("1) execute_tool called directly with a nonexistent trial ID:")
    print("   ", execute_tool("get_trial_details", {"trial_id": 999999}))
    print("2) agent asked about the same impossible ID:")
    prompt = "Give me the full details of clinical trial 999999."
    print(f"   prompt: {prompt}")
    result = agent.run_agent(prompt, run_id="recover-999999")
    show_result(result)
    print("   agent returned normally (no crash).")


def cmd_reliability(args) -> None:
    banner("HW7 Part 2: reliability")
    tag = "_injected" if args.inject_every else ""
    log_path = RAW / f"reliability{tag}_tool_log.jsonl"
    injector = (
        reliability.FaultInjector(args.inject_every) if args.inject_every else None
    )
    reset_log(log_path)
    if injector:
        print(
            f"FAULT INJECTION ON: every {args.inject_every}th tool-call reply is "
            "corrupted before validation (test only, not real model errors)"
        )
    print(
        f"{args.attempts} attempts, temperature {args.temperature}, "
        f"seed = {config.SEED} + attempt number"
    )
    rows = []
    for attempt in range(args.attempts):
        case = cases.CASES[attempt % len(cases.CASES)]
        row = reliability.run_attempt(
            case,
            attempt,
            seed=config.SEED + attempt,
            temperature=args.temperature,
            log_path=log_path,
            injector=injector,
        )
        rows.append(row)
        print(
            f"  attempt {attempt + 1:2d}/{args.attempts} case {case['id']} "
            f"seed {row['seed']}: calls {row['tool_calls']}, "
            f"first-try ok {row['first_try_ok']}/{row['call_attempts']}, "
            f"injected {row['injected']}, "
            f"repairs {row['repair_ok']}/{row['repair_attempts']}, "
            f"chain {'ok' if row['chain_ok'] else 'LOST'}, {row['stop_reason']}"
        )
        if row["stop_reason"] == "model_error":
            print(f"  model error: {row['answer']}")
            print("  Is Ollama running with the model pulled? Stopping.")
            return
    summary = reliability.summarize(rows)
    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / f"reliability{tag}_attempts.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    flat = [k for k in rows[0] if k not in ("answer", "tool_log")]
    with (RAW / f"reliability{tag}_attempts.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=flat)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in flat})
    (RAW / f"reliability{tag}_summary.json").write_text(json.dumps(summary, indent=2))
    print("-" * 78)
    print(f"Tool-call attempts: {summary['tool_call_attempts']}")
    print(f"Faults injected: {summary['faults_injected']}")
    before, after = summary["rate_before_repair"], summary["rate_after_repair"]
    print(
        f"Well-formed before repair: "
        f"{summary['well_formed_before_repair']} ({before:.1%})"
    )
    print(
        f"Well-formed after repair:  "
        f"{summary['well_formed_after_repair']} ({after:.1%})"
    )
    print("Failures by class:")
    for name, count in summary["failures_by_class"].items():
        print(f"  {name}: {count}")
    print(
        f"Chains completed: {summary['chains_completed']}/{summary['attempts']} | "
        f"answers correct: {summary['answers_correct']}/{summary['attempts']}"
    )
    print("Saved raw data to reports/hw07/raw/ (reliability_*)")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tasks").set_defaults(func=cmd_tasks)
    sub.add_parser("recover").set_defaults(func=cmd_recover)
    rel = sub.add_parser("reliability")
    rel.add_argument("--attempts", type=int, default=21)
    rel.add_argument("--temperature", type=float, default=0.3)
    rel.add_argument("--inject-every", type=int, default=0)
    rel.set_defaults(func=cmd_reliability)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
