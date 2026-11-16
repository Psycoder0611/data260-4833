"""HW10 Part 3 step 2: give each of the 20 drafts YOUR helpfulness label, 1 to 5.

    python label_hw10_cases.py

Shows the question, the facts the Writer was given and the draft, and asks for a number.
Nothing from any model (no judge score, no reviewer score) is shown. Labels are written to
data/hw10/human_labels.csv one at a time, so you can stop with q and continue later. A label
that is already saved is never changed by this script.

Guide (the same wording is used for the judge):
  5 fully helpful: correct, clear and complete for the question
  4 helpful: correct for the question, only minor gaps
  3 partly helpful: relevant but incomplete, vague or with small errors
  2 mostly unhelpful: major gaps or clear errors
  1 unhelpful: wrong, off-topic or empty
"""

import csv
import json
import textwrap
import time

from hw10 import config

GUIDE = __doc__.split("Guide")[1]


def main() -> None:
    """Ask for the missing labels."""
    cases = json.loads(config.CASES_PATH.read_text(encoding="utf-8"))["cases"]
    done = {}
    if config.LABELS_PATH.exists():
        with open(config.LABELS_PATH, encoding="utf-8") as handle:
            done = {r["case_id"]: r for r in csv.DictReader(handle)}
    new_file = not config.LABELS_PATH.exists()
    todo = [c for c in cases if c["case_id"] not in done]
    print(f"{len(done)} of {len(cases)} labeled, {len(todo)} to go. Type 1-5, or q to stop.")
    print("Guide" + GUIDE)
    with open(config.LABELS_PATH, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["case_id", "human_score", "labeled_at"])
        for case in todo:
            print("=" * 78)
            print(f"{case['case_id']}  QUESTION: {case['question']}")
            if case["facts"]:
                print("FACTS GIVEN TO THE WRITER:", case["facts"])
            print("DRAFT:")
            print(textwrap.indent(textwrap.fill(case["draft"], 76), "  "))
            while True:
                answer = input("your score (1-5, q = stop): ").strip().lower()
                if answer == "q":
                    print("Stopped. Run the script again to continue.")
                    return
                if answer in {"1", "2", "3", "4", "5"}:
                    writer.writerow([case["case_id"], answer, time.strftime("%Y-%m-%d %H:%M:%S")])
                    handle.flush()
                    break
                print("Please type a whole number from 1 to 5.")
    print("All 20 labeled. Next: git add data/hw10/eval_cases.json data/hw10/human_labels.csv and commit them, then run the judge.")


if __name__ == "__main__":
    main()
