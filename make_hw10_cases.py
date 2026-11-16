"""HW10 Part 3 step 1: create data/hw10/eval_cases.json (20 Writer drafts).

    python make_hw10_cases.py

Each case is a question that the domain assistant (Clinical Trial Listings) receives, the
Planner's plan and the Writer's draft, produced by the same HW8 Planner and Writer roles
(local qwen3:8b, temperature 0, seed 4833). The questions are a deliberate mix: listing
lookups that use database facts, general trial questions, and a few vague, unanswerable or
off-topic ones so the drafts do not all look alike. No score of any kind is stored here.
After this, label the drafts yourself with label_hw10_cases.py and commit both files.
"""

import json
import sys
import time

from hw8 import config as hw8_config
from hw8.pipeline import Brain
from hw9 import facts
from hw9.agent_backend import HW8Agents

from hw10 import config
from hw10.logs import run_logged
from hw10.runtime import make_engine

QUESTIONS = [
    "What is the participant capacity of trial CT-2026-101?",
    "Who sponsors trial CT-2026-102 and what is its title?",
    "Which category is trial CT-2026-103 listed under?",
    "Give me a one-line summary of trial CT-2026-104.",
    "Tell me everything about trial CT-2026-105.",
    "What is the capacity of trial CT-2026-999?",
    "What does a Phase II clinical trial test?",
    "Explain informed consent to a first-time participant.",
    "How do I know if a trial listing is still recruiting?",
    "What is a placebo and why is it used?",
    "Can I join a trial if I am taking other medication?",
    "Is it safe to take part in a clinical trial?",
    "What should I ask before enrolling in a trial?",
    "How is a trial sponsor different from a principal investigator?",
    "Compare trials CT-2026-101 and CT-2026-102 by capacity.",
    "Which trial is best for me?",
    "Trials?",
    "What is the weather in San Jose today?",
    "Write a poem about clinical trials.",
    "Does the platform guarantee that a trial will cure my condition?",
]


def main() -> None:
    """Build the cases with the real model and save them."""
    if config.CASES_PATH.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{config.CASES_PATH} already exists. It is the frozen set; delete it yourself only before labeling.")
    engine = make_engine()
    agents = HW8Agents(Brain(mode="ollama"))
    cases = []
    for i, question in enumerate(QUESTIONS, 1):
        facts_text, _, _ = facts.facts_for(engine, question)
        model_input = question
        if facts_text:
            model_input = f"{question}\n\nFacts from the listings database (use them exactly):\n{facts_text}"
        payload = {"question": model_input}
        plan = agents._retry(agents.brain.plan, payload)
        draft = agents._retry(agents.brain.write, payload, plan)
        cases.append({
            "case_id": f"C{i:02d}",
            "question": question,
            "facts": facts_text,
            "judge_input": model_input,
            "plan": plan,
            "draft": draft,
        })
        print(f"C{i:02d} ok: {question[:60]}")
    config.CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.CASES_PATH.write_text(json.dumps({
        "domain": config.DOMAIN_NAME,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "writer_model": hw8_config.MODEL_NAME,
        "temperature": hw8_config.TEMPERATURE,
        "seed": config.SEED,
        "cases": cases,
    }, indent=2), encoding="utf-8")
    print(f"Saved {len(cases)} cases to {config.CASES_PATH}")


if __name__ == "__main__":
    with run_logged("make eval cases"):
        main()
