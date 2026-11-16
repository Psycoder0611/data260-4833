"""HW10 Part 3: validate the judge against my own labels, then check repeatability.

    python run_hw10_part3.py all        judge run 1, 2 and 3, then the statistics
    python run_hw10_part3.py run 1      one judge run (1, 2 or 3)
    python run_hw10_part3.py stats      recompute the statistics from the saved runs

Refuses to start unless data/hw10/eval_cases.json and data/hw10/human_labels.csv are
committed in git and unchanged since (a read-only git check), so the judge can never
influence the labels. Judge scores go to reports/hw10/raw/ only; the two input files are
never written by this script.
"""

import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from hw10 import config, stats
from hw10.judge import score_text
from hw10.logs import run_logged
from hw10.preflight import check_ollama
from hw10.runtime import make_judge

ROOT = Path(__file__).resolve().parent


def git(*args: str) -> str:
    """Output of a read-only git command ('' if it fails)."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def load_inputs() -> Dict[str, Any]:
    """Load the 20 cases and the 20 labels and check them."""
    cases = json.loads(config.CASES_PATH.read_text(encoding="utf-8"))["cases"]
    with open(config.LABELS_PATH, encoding="utf-8") as handle:
        labels = {r["case_id"]: int(r["human_score"]) for r in csv.DictReader(handle)}
    ids = [c["case_id"] for c in cases]
    if len(cases) != 20 or sorted(labels) != sorted(ids):
        raise SystemExit(f"Need 20 cases and 20 labels with the same case_ids (have {len(cases)} cases, {len(labels)} labels).")
    if not all(1 <= v <= 5 for v in labels.values()):
        raise SystemExit("Every human label must be a whole number from 1 to 5.")
    return {"cases": cases, "labels": labels}


def committed_state() -> Dict[str, str]:
    """Prove that both input files are committed and unchanged; return the commit."""
    rels = [str(p.relative_to(ROOT)) for p in (config.CASES_PATH, config.LABELS_PATH)]
    for rel in rels:
        if not git("ls-files", "--error-unmatch", rel):
            raise SystemExit(f"{rel} is not committed yet. Commit eval_cases.json and human_labels.csv first, then run the judge.")
    dirty = git("status", "--porcelain", "--", *rels)
    if dirty:
        raise SystemExit(f"These files changed after the commit:\n{dirty}\nCommit them (or undo the change) before running the judge.")
    commit = git("log", "-1", "--format=%H", "--", *rels)
    when = git("log", "-1", "--format=%cI", "--", *rels)
    return {"commit": commit, "committed_at": when}


def run_path(n: int) -> Path:
    """File of judge run n."""
    return config.RAW_DIR / f"part3_judge_run{n}.json"


def judge_run(n: int) -> None:
    """Score the 20 drafts once and save the raw scores."""
    inputs = load_inputs()
    state = committed_state()
    problems = check_ollama([config.JUDGE_MODEL])
    if problems:
        raise SystemExit("\n".join(problems))
    judge = make_judge()
    print(f"Judge run {n}: model={config.JUDGE_MODEL} temperature={config.JUDGE_TEMPERATURE} seed={config.JUDGE_SEED}; inputs committed in {state['commit'][:10]}")
    results: Dict[str, Any] = {}
    for case in inputs["cases"]:
        started = time.time()
        res = score_text("helpfulness", case["judge_input"], case["draft"], judge)
        res["seconds"] = round(time.time() - started, 1)
        results[case["case_id"]] = res
        print(f"  {case['case_id']}: human {inputs['labels'][case['case_id']]}  judge {res['score']}  ({res['status']}, {res['seconds']}s)")
    run_path(n).parent.mkdir(parents=True, exist_ok=True)
    run_path(n).write_text(json.dumps({
        "run": n, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "judge_model": config.JUDGE_MODEL,
        "temperature": config.JUDGE_TEMPERATURE, "seed": config.JUDGE_SEED, "inputs_commit": state, "results": results,
    }, indent=2), encoding="utf-8")


def compute_stats() -> None:
    """Spearman, MAD and repeatability from the saved runs; writes part3_validation.json and a CSV."""
    inputs = load_inputs()
    runs: List[Dict[str, Any]] = []
    n = 1
    while run_path(n).exists():
        runs.append(json.loads(run_path(n).read_text(encoding="utf-8")))
        n += 1
    if not runs:
        raise SystemExit("No judge run saved yet (python run_hw10_part3.py all).")
    ids = [c["case_id"] for c in inputs["cases"]]
    human = [inputs["labels"][i] for i in ids]
    first = {i: runs[0]["results"][i]["score"] for i in ids}
    validation = stats.validation_stats(human, [first[i] for i in ids])
    repeat = stats.repeatability([{i: r["results"][i]["score"] for i in ids} for r in runs])
    cases = []
    for case in inputs["cases"]:
        cid = case["case_id"]
        row = {"case_id": cid, "question": case["question"][:70], "human_score": inputs["labels"][cid]}
        for r in runs:
            row[f"judge_run{r['run']}"] = r["results"][cid]["score"]
        row["abs_diff_run1"] = abs(inputs["labels"][cid] - first[cid]) if first[cid] is not None else None
        row["judge_reason_run1"] = runs[0]["results"][cid]["reason"]
        cases.append(row)
    out = {
        "judge_model": config.JUDGE_MODEL, "scale": "1-5 integer (same as human labels)",
        "validation_run": 1, "validation": validation, "repeatability": repeat, "cases": cases,
        "inputs_commit": runs[0].get("inputs_commit"),
    }
    (config.RAW_DIR / "part3_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    csv_path = config.RAW_DIR / "part3_per_case.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    print(json.dumps({"validation": validation, "repeatability": {k: v for k, v in repeat.items() if k != "per_case_spread"}}, indent=2))
    print(f"Saved {config.RAW_DIR / 'part3_validation.json'} and {csv_path}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    with run_logged(f"part 3 judge validation ({command})"):
        if command == "all":
            for number in (1, 2, 3):
                judge_run(number)
            compute_stats()
        elif command == "run":
            judge_run(int(sys.argv[2]))
        elif command == "stats":
            compute_stats()
        else:
            raise SystemExit(__doc__)
