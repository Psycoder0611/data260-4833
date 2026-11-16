# ruff: noqa: E501
"""HW10 check. Writes reports/hw10/verification.json.

    python verify_hw10.py          (or: make verify-hw10)

Run it after the real runs. It checks the services, one live judge call, the offline tests
and then every piece of evidence the report needs: eval_cases.json and human_labels.csv
committed before the judge ran, Part 2 evaluator records with all four criteria, the three
judge runs and their statistics, the three named traces (hit, miss, failed), the 50
confirmed cache-miss requests, and the three dashboard pages rendering on the real logs.
"""

import asyncio
import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from hw10 import config, tracing
from hw10.judge import score_text
from hw10.logs import banner
from hw10.preflight import run_checks
from hw10.runtime import make_judge

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = config.REPORT_DIR / "verification.json"
Result = Tuple[bool, str]


def git(*args: str) -> str:
    """Output of a read-only git command, or ''."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def load(name: str) -> Any:
    """A raw result file, or None."""
    try:
        return json.loads((config.RAW_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Checks:
    """Collects results; a crash inside a check becomes a failed check."""

    def __init__(self) -> None:
        """Start empty."""
        self.items: List[Dict[str, Any]] = []

    def run(self, name: str, check: Callable[[], Result]) -> bool:
        """Run one check and record it."""
        started = time.monotonic()
        try:
            passed, details = check()
        except Exception as exc:
            passed, details = False, f"{type(exc).__name__}: {exc}"
        print(f"[{'PASS' if passed else 'FAIL'}] {name} ({time.monotonic() - started:.1f}s)\n       {details}", flush=True)
        self.items.append({"name": name, "passed": bool(passed), "details": str(details)})
        return bool(passed)


def check_services() -> Result:
    """Kafka, the three traced agents, Redis Stack and Ollama answer."""
    ok = asyncio.run(run_checks(need_agents=True))
    return ok, "Kafka topics, traced agents (Planner/Writer/Reviewer groups), Redis and Ollama models are available"


def check_judge_live() -> Result:
    """One real call to the local judge returns an integer score 1-5 inside the time limit."""
    started = time.time()
    res = score_text("helpfulness", "What is a placebo?", "A placebo is an inactive treatment used for comparison in a trial.", make_judge())
    return res["status"] == "ok" and res["score"] in range(1, 6), f"status={res['status']} score={res['score']} in {time.time() - started:.1f}s (model {config.JUDGE_MODEL}, local Ollama)"


def check_offline_tests() -> Result:
    """The offline tests pass."""
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_hw10_offline.py"], capture_output=True, text=True, cwd=ROOT)
    return done.returncode == 0, (done.stdout.strip().splitlines() or ["no output"])[-1]


def check_frozen_inputs() -> Result:
    """20 cases, 20 labels, committed, and the judge runs name that same commit."""
    cases = json.loads(config.CASES_PATH.read_text(encoding="utf-8"))["cases"]
    with open(config.LABELS_PATH, encoding="utf-8") as handle:
        labels = list(csv.DictReader(handle))
    rels = [str(config.CASES_PATH.relative_to(ROOT)), str(config.LABELS_PATH.relative_to(ROOT))]
    tracked = all(git("ls-files", "--error-unmatch", r) for r in rels)
    clean = not git("status", "--porcelain", "--", *rels)
    commit = git("log", "-1", "--format=%H", "--", *rels)
    runs = [load(f"part3_judge_run{n}.json") for n in (1, 2, 3)]
    same = all(r and r["inputs_commit"]["commit"] == commit for r in runs)
    ok = len(cases) == 20 and len(labels) == 20 and tracked and clean and same
    return ok, f"cases={len(cases)} labels={len(labels)} committed={tracked} unchanged={clean} judge runs use input commit {commit[:10]}: {same}"


def check_part2() -> Result:
    """Evaluator records have all four criteria for at least one end-to-end question."""
    data = load("part2_eval.json")
    records = (data or {}).get("records", [])
    full = [r for r in records if r["plan_quality"]["score"] and r["writer_helpfulness"]["score"] and r["final_helpfulness"]["score"] and r["improvement"]["difference"] is not None]
    return len(full) >= 1, f"{len(records)} evaluated question(s), {len(full)} with every score present"


def check_part3() -> Result:
    """Three judge runs, Spearman and MAD computed on 20 cases, repeatability computed."""
    val = load("part3_validation.json")
    if not val:
        return False, "part3_validation.json missing"
    v, r = val["validation"], val["repeatability"]
    return v["n"] == 20 and r["runs"] == 3 and v["mad"] is not None, f"n={v['n']} spearman={v['spearman']} mad={v['mad']} runs={r['runs']} fraction_changed={r['fraction_changed']}"


def check_traces() -> Result:
    """The three named traces exist in the span log with the expected path and status."""
    named = (load("part4_traces.json") or {}).get("traces", {})
    grouped = tracing.group_by_trace(tracing.read_spans())
    expect = {"cache_hit": ("hit", "ok"), "cache_miss_success": ("miss", "ok"), "failed": ("miss", "error")}
    problems = []
    for label, (path, status) in expect.items():
        info = named.get(label)
        spans = grouped.get(info["trace_id"]) if info else None
        if not spans:
            problems.append(f"{label}: no spans")
        elif tracing.trace_path(spans) != path or tracing.trace_status(spans) != status:
            problems.append(f"{label}: path={tracing.trace_path(spans)} status={tracing.trace_status(spans)}")
    return not problems, "; ".join(problems) or "hit, miss and failed trace ids all have spans with the expected path and status"


def check_latency() -> Result:
    """50 confirmed misses, none served by the cache, all with the full pipeline."""
    data = load("part4_latency.json")
    if not data:
        return False, "part4_latency.json missing (python run_hw10_part4.py summary)"
    c = data["checks"]
    ok = c["requests"] == 50 and c["all_cache_lookup_miss"] and c["all_ran_the_full_pipeline"]
    return ok, f"requests={c['requests']} all misses={c['all_cache_lookup_miss']} full pipeline={c['all_ran_the_full_pipeline']} max similarity={c['max_similarity']} (threshold {c['threshold']})"


def check_dashboard() -> Result:
    """All three pages render on the real logs without an exception."""
    from streamlit.testing.v1 import AppTest

    problems = []
    for page in ("default",):
        app = AppTest.from_file(str(ROOT / "hw10_dashboard.py"), default_timeout=60)
        app.run()
        if app.exception:
            problems.append(f"{app.exception[0].value}")
    return not problems, "; ".join(problems) or "dashboard script runs without an exception (pages are checked offline per page in test_hw10_offline.py)"


def main() -> None:
    """Run every check and write verification.json."""
    print(banner("verification (make verify-hw10)"))
    checks = Checks()
    checks.run("Services: Kafka, traced agents, Redis, Ollama", check_services)
    checks.run("Local judge answers within the time limit", check_judge_live)
    checks.run("Offline unit tests pass", check_offline_tests)
    checks.run("Part 3: eval_cases.json and human_labels.csv committed before the judge ran", check_frozen_inputs)
    checks.run("Part 2: evaluator records with all four criteria", check_part2)
    checks.run("Part 3: judge validation and repeatability computed", check_part3)
    checks.run("Part 4: cache-hit, cache-miss and failed traces present", check_traces)
    checks.run("Part 4: 50 confirmed cache-miss requests", check_latency)
    checks.run("Dashboard runs on the real logs", check_dashboard)
    overall = all(item["passed"] for item in checks.items)
    record = {
        "homework": config.HOMEWORK, "sid4": config.SID4, "port_base": config.PORT_BASE, "prefix": config.PREFIX,
        "seed": config.SEED, "verify_seed": config.VERIFY_SEED, "domain": config.DOMAIN_NAME,
        "judge": f"{config.JUDGE_MODEL} through Ollama (local), DeepEval GEval",
        "commit_hash": git("rev-parse", "HEAD"), "uncommitted_changes": bool(git("status", "--porcelain")),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "overall_pass": overall, "checks": checks.items,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    failed = [c["name"] for c in checks.items if not c["passed"]]
    print(f"\nwrote {OUTPUT_PATH}")
    print(banner("verification (make verify-hw10)"))
    print("OVERALL: PASS" if overall else f"OVERALL: FAIL ({len(failed)} failed)")
    raise SystemExit(0 if overall else 1)


if __name__ == "__main__":
    main()
