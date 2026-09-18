"""
DATA 260 - Homework 3
Self-check script for HW3 deliverables.

This script performs objective checks and writes:
reports/hw03/verification.json
"""

import json
import py_compile
from pathlib import Path
import pandas as pd
import yaml

SID4 = 4833
VERIFY_SEED = 264833

REPORT_DIR = Path("reports/hw03")
RAW_DIR = REPORT_DIR / "raw"
DATA_DIR = Path("data/hw03")

checks = []


def add_check(name, passed, details):
    checks.append({
        "check": name,
        "passed": bool(passed),
        "details": details
    })


def main():
    # 1. Python files compile
    compile_targets = [
        Path("main.py"),
        Path("routers/auth.py"),
        Path("run_hw03_retrieval.py"),
        Path("compute_hw03_metrics.py"),
    ]

    compile_ok = True
    compile_details = []

    for path in compile_targets:
        try:
            py_compile.compile(str(path), doraise=True)
            compile_details.append(f"{path}: PASS")
        except Exception as exc:
            compile_ok = False
            compile_details.append(f"{path}: FAIL ({exc})")

    add_check(
        "Python files compile",
        compile_ok,
        "; ".join(compile_details)
    )

    # 2. Corpus exists and is at least 200 KB total
    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    total_bytes = sum(path.stat().st_size for path in pdf_files)

    add_check(
        "Corpus size and PDF count",
        len(pdf_files) == 3 and total_bytes >= 200 * 1024,
        f"{len(pdf_files)} PDFs, {total_bytes} bytes total"
    )

    # 3. questions.yaml contains exactly five questions
    questions_path = REPORT_DIR / "questions.yaml"

    try:
        data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
        questions = data.get("questions", [])
        questions_ok = len(questions) == 5
        details = f"{len(questions)} questions found"
    except Exception as exc:
        questions_ok = False
        details = f"Could not read questions.yaml: {exc}"

    add_check(
        "Five precommitted retrieval questions",
        questions_ok,
        details
    )

    # 4. Required raw retrieval CSV files exist and contain results
    raw_files = {
        "Token": RAW_DIR / "token_retrieval.csv",
        "Semantic": RAW_DIR / "semantic_retrieval.csv",
        "Sentence-Window": RAW_DIR / "sentence_window_retrieval.csv",
    }

    raw_ok = True
    raw_details = []

    for name, path in raw_files.items():
        if not path.exists():
            raw_ok = False
            raw_details.append(f"{name}: missing")
            continue

        try:
            df = pd.read_csv(path)
            required_columns = {
                "question_id",
                "rank",
                "source_file",
                "store_score",
                "cosine_sim",
                "chunk_len",
                "retrieval_latency_ms",
            }

            has_columns = required_columns.issubset(df.columns)
            has_rows = len(df) == 15  # 5 questions x top-3 results

            if not (has_columns and has_rows):
                raw_ok = False

            raw_details.append(
                f"{name}: {len(df)} rows, required columns={has_columns}"
            )
        except Exception as exc:
            raw_ok = False
            raw_details.append(f"{name}: FAIL ({exc})")

    add_check(
        "Raw retrieval outputs",
        raw_ok,
        "; ".join(raw_details)
    )

    # 5. Every technique achieves expected-source Recall@3 = 1.0
    recall_ok = True
    recall_details = []

    for name, path in raw_files.items():
        try:
            df = pd.read_csv(path)
            question_ids = df["question_id"].unique()
            hits = 0

            for qid in question_ids:
                q_df = (
                    df[df["question_id"] == qid]
                    .sort_values("rank")
                    .head(3)
                )
                expected = q_df["expected_source"].iloc[0]

                if expected in set(q_df["source_file"]):
                    hits += 1

            recall = hits / len(question_ids)
            recall_details.append(f"{name}: Recall@3={recall:.2f}")

            if recall != 1.0:
                recall_ok = False

        except Exception as exc:
            recall_ok = False
            recall_details.append(f"{name}: FAIL ({exc})")

    add_check(
        "Recall@3 verification",
        recall_ok,
        "; ".join(recall_details)
    )

    # 6. Required documentation files exist and are non-empty
    required_docs = [
        REPORT_DIR / "SOURCES.md",
        REPORT_DIR / "CORPUS_MANIFEST.json",
        REPORT_DIR / "questions.yaml",
        REPORT_DIR / "METRICS.md",
        REPORT_DIR / "RUN_LOG.txt",
        REPORT_DIR / "AI_USE.md",
    ]

    docs_ok = all(
        path.exists() and path.stat().st_size > 0
        for path in required_docs
    )

    add_check(
        "Required HW3 documentation files",
        docs_ok,
        ", ".join(
            f"{path.name}={'PASS' if path.exists() and path.stat().st_size > 0 else 'FAIL'}"
            for path in required_docs
        )
    )

    all_passed = all(item["passed"] for item in checks)

    output = {
        "homework": 3,
        "sid4": SID4,
        "verify_seed": VERIFY_SEED,
        "all_passed": all_passed,
        "checks": checks
    }

    output_path = REPORT_DIR / "verification.json"
    output_path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print("=" * 70)
    print("HW3 VERIFICATION")
    print("=" * 70)

    for item in checks:
        status = "PASS" if item["passed"] else "FAIL"
        print(f"[{status}] {item['check']}")
        print(f"       {item['details']}")

    print()
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")
    print(f"Saved verification output to: {output_path}")


if __name__ == "__main__":
    main()
