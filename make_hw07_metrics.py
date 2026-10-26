"""Write reports/hw07/METRICS.md from the saved raw results (no model needed).

Run:  python make_hw07_metrics.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "reports" / "hw07" / "raw"
OUT = ROOT / "reports" / "hw07" / "METRICS.md"


def load(name):
    """Read one raw JSON file."""
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def table(rows):
    """Markdown table from a list of rows; the first row is the header."""
    lines = ["| " + " | ".join(str(c) for c in rows[0]) + " |"]
    lines.append("|" + "|".join("---" for _ in rows[0]) + "|")
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def part2():
    """Reliability tables (normal run and run with injected faults)."""
    real = load("reliability_summary.json")
    fault = load("reliability_injected_summary.json")
    rows = [["Metric", "Normal run", "With injected faults"]]
    rows += [
        ["Attempts", real["attempts"], fault["attempts"]],
        ["Tool-call attempts", real["tool_call_attempts"], fault["tool_call_attempts"]],
        ["Faults injected", 0, fault["faults_injected"]],
        [
            "Well-formed before repair",
            f"{real['well_formed_before_repair']} ({real['rate_before_repair']:.0%})",
            f"{fault['well_formed_before_repair']} ({fault['rate_before_repair']:.0%})",
        ],
        [
            "Well-formed after repair",
            f"{real['well_formed_after_repair']} ({real['rate_after_repair']:.0%})",
            f"{fault['well_formed_after_repair']} ({fault['rate_after_repair']:.0%})",
        ],
    ]
    for key, label in [
        ("malformed_arguments", "Failures: malformed arguments"),
        ("unknown_tool", "Failures: unknown tool"),
        ("text_when_tool_required", "Failures: text when a tool was required"),
        ("lost_multi_step_chain", "Failures: lost multi-step chain"),
    ]:
        rows.append(
            [label, real["failures_by_class"][key], fault["failures_by_class"][key]]
        )
    rows += [
        [
            "Chains completed",
            f"{real['chains_completed']}/21",
            f"{fault['chains_completed']}/21",
        ],
        [
            "Answers correct",
            f"{real['answers_correct']}/21",
            f"{fault['answers_correct']}/21",
        ],
        [
            "Average tool calls per attempt",
            real["avg_tool_calls"],
            fault["avg_tool_calls"],
        ],
        ["Total tokens", f"{real['total_tokens']:,}", f"{fault['total_tokens']:,}"],
        [
            "Average model latency (ms)",
            f"{real['avg_model_latency_ms']:,.0f}",
            f"{fault['avg_model_latency_ms']:,.0f}",
        ],
    ]
    return "## Part 2 - Tool-call reliability (21 attempts, 7 per task)\n\n" + table(
        rows
    )


def part3():
    """Original loop vs Reflexion loop."""
    data = load("reflexion_draft_comparison.json")
    n = data["runs"]
    o, r = data["original"], data["reflexion"]
    rows = [
        ["Metric", "Original loop", "Reflexion loop"],
        ["Task success", f"{o['task_success']}/{n}", f"{r['task_success']}/{n}"],
        ["Unsupported claims", o["unsupported_claims"], r["unsupported_claims"]],
        ["Retry rate", "n/a (no retries)", f"{r['retry_rate']:.1%}"],
        ["Tool calls (total)", o["tool_calls"], r["tool_calls"]],
        ["Tokens (total)", f"{o['tokens']:,}", f"{r['tokens']:,}"],
        ["Latency ms (total)", f"{o['latency_ms']:,.0f}", f"{r['latency_ms']:,.0f}"],
        [
            "Verifier rejected a successful answer",
            "0 after review (7 disagreements)",
            "0 after review (the same 7)",
        ],
    ]
    note = (
        "\n\nThe 7 disagreements are all Task B, where the verifier wanted an example "
        "trial named and the Part 2 check did not; they were reviewed by hand."
    )
    return "## Part 3 - Original vs Reflexion (same 21 tasks)\n\n" + table(rows) + note


def part4():
    """Bike scenarios: totals, decisions and run metrics."""
    rows = [["Item", "Scenario A (membership)", "Scenario B (pay per use)"]]
    runs = {
        k: load(f"bike_scenario_{k}_run.json")["result"]
        for k in ("a_membership", "b_payperuse")
    }
    snaps = {
        k: load(f"pricing_snapshot_scenario_{k}.json")
        for k in ("a_membership", "b_payperuse")
    }
    a, b = runs["a_membership"], runs["b_payperuse"]
    rows += [
        ["Rider R001 rides", a["actual_rides"], b["actual_rides"]],
        [
            "Pay-per-use total",
            f"${a['pay_per_use_total']}",
            f"${b['pay_per_use_total']}",
        ],
        ["Membership total", f"${a['membership_total']}", f"${b['membership_total']}"],
        ["Break-even rides (agent)", a["break_even_rides"], b["break_even_rides"]],
        [
            "Break-even rides (reference)",
            a["reference"]["break_even_rides"],
            b["reference"]["break_even_rides"],
        ],
        ["Decision", a["decision"], b["decision"]],
        ["Steps", a["steps"], b["steps"]],
        ["Total time (s)", a["total_seconds"], b["total_seconds"]],
        ["Tool calls", a["tool_calls"], b["tool_calls"]],
        ["Replies rejected", a["repairs"], b["repairs"]],
        ["Stop reason", a["stop_reason"], b["stop_reason"]],
        ["Tokens", f"{a['tokens']:,}", f"{b['tokens']:,}"],
        [
            "Outside checks",
            "all pass" if all(a["checks"].values()) else a["checks"],
            "all pass" if all(b["checks"].values()) else b["checks"],
        ],
        [
            "CSV rows (SHA-256 of file)",
            f"{a['csv_rows']} ({a['csv_sha256'][:12]}...)",
            f"{b['csv_rows']} ({b['csv_sha256'][:12]}...)",
        ],
        [
            "Pricing snapshot SHA-256",
            snaps["a_membership"]["sha256"][:16] + "...",
            snaps["b_payperuse"]["sha256"][:16] + "...",
        ],
        ["Pricing source", snaps["a_membership"]["url"], snaps["b_payperuse"]["url"]],
        [
            "Snapshot access time (UTC)",
            snaps["a_membership"]["access_ts"],
            snaps["b_payperuse"]["access_ts"],
        ],
    ]
    return "## Part 4 - Bay Wheels scenarios (last saved runs)\n\n" + table(rows)


def counts(results):
    """Rows of attack-success counts per setting."""
    rows = [
        [
            "Setting",
            "Fee from page used",
            "Decision flipped",
            "Write sent",
            "Other rider's ids leaked",
            "Runs finished",
        ]
    ]
    names = {
        "before": "No defenses",
        "prompt": "Prompt label",
        "full": "Prompt label + read-only tool",
    }
    for cfg, name in names.items():
        rs = [r for r in results if r["config"] == cfg]
        if not rs:
            continue
        n = len(rs)
        rows.append(
            [
                name,
                f"{sum(r['override']['poisoned_fee_used'] for r in rs)}/{n}",
                f"{sum(r['override']['decision_flipped'] for r in rs)}/{n}",
                f"{sum(r['misuse']['attempted'] for r in rs)}/{n}",
                f"{sum(r['exfil']['success'] for r in rs)}/{n}",
                f"{sum(r['finished'] for r in rs)}/{n}",
            ]
        )
    return rows


def part5():
    """Attack results: live model on the hostile page, clean-page control, stand-in."""
    out = ["## Part 5 - Prompt injection (rider R001, Scenario B, temperature 0.3)\n"]
    out.append("Live qwen3:8b on the hostile page (5 runs per setting):\n")
    out.append(table(counts(load("part5_hostile_results.json"))))
    out.append("\nControl: live model on the clean page (3 runs per setting):\n")
    out.append(table(counts(load("part5_clean_results.json"))))
    standin = {r["config"]: r for r in load("part5_standin_results.json")}
    rows = [["Attack", "Before defenses", "After prompt + tool defense"]]
    for key, label in [
        ("override", "Recommendation override"),
        ("misuse", "Non-SELECT tool misuse"),
        ("exfil", "Data exfiltration"),
    ]:
        rows.append(
            [
                label,
                "succeeded" if standin["before"][key]["success"] else "failed",
                "succeeded" if standin["full"][key]["success"] else "failed",
            ]
        )
    rows.append(
        [
            "Rows in trips (before -> after)",
            f"{standin['before']['misuse']['rows_before']} -> "
            f"{standin['before']['misuse']['rows_after']}",
            f"{standin['full']['misuse']['rows_before']} -> "
            f"{standin['full']['misuse']['rows_after']}",
        ]
    )
    out.append("\nScripted stand-in model that obeys the page (1 run per setting):\n")
    out.append(table(rows))
    out.append(
        "\nThe stand-in only tests the two attacks the live model never tried "
        "(misuse and exfiltration). The override attack is measured on the live "
        "model above."
    )
    return "\n".join(out)


def part6():
    """Ten-command safety gate."""
    rows = [["Command", "Expected", "Gate said", "Reason", "Correct"]]
    results = load("part6_gate_results.json")
    for r in results:
        rows.append(
            [
                f"`{r['command']}`",
                r["expected"],
                "allow" if r["allow"] else "block",
                r["reason"],
                "yes" if r["ok"] else "NO",
            ]
        )
    right = sum(r["ok"] for r in results)
    false_allows = sum(r["expected"] == "block" and r["allow"] for r in results)
    return (
        "## Part 6 - Safety gate (5 allowed, 5 blocked)\n\n"
        + table(rows)
        + f"\n\nCorrect: {right}/{len(results)}. False allows: {false_allows}."
    )


def main():
    """Write METRICS.md."""
    text = "# HW7 metrics - Trapti Kulshrestha (SID4 4833)\n\n"
    text += "\n\n".join([part2(), part3(), part4(), part5(), part6()]) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
