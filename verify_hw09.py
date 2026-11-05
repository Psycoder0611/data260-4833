# ruff: noqa: E501
"""HW9 smoke test. Writes reports/hw09/verification.json.

Needs Redis Stack (docker compose -f docker-compose.hw9.yml up -d), Ollama with
nomic-embed-text and the s4833_rel MySQL database. It checks the basics of every part:

  Part 1  the view counter counts, uses an s4833: key and syncs to the database
          on every 10th access
  Part 2  the vector index finds an exact duplicate (similarity ~1) and ranks an
          unrelated question lower; HIT/MISS flags come back
  Part 3  cache_cases.yaml has 40 labeled cases; a stale answer is served without
          invalidation and refreshed with the data-version check
  Part 4  datasets contain only questions; the reference dataset loads; lessons.json
          has the required fields; the four-variant result file exists
  Other   the offline tests pass; evidence files exist

The agents here use the stub model, so the check is quick and does not depend on what
qwen3:8b says. Temporary changes to the database (view_count, one capacity) are
restored at the end.

Run:  python verify_hw09.py          (or: make verify-hw09)
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import yaml

from hw8.pipeline import Brain
from hw9 import config, db
from hw9.agent_backend import HW8Agents
from hw9.cache_db import ClinicalTrialCache
from hw9.logs import banner
from hw9.qa_service import QAService
from hw9.runtime import make_binary_redis, make_cache

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = config.REPORT_DIR / "verification.json"
Result = Tuple[bool, str]
CODE = "CT-2026-105"


def git_output(*args: str) -> str:
    """Return the output of a read-only git command, or '' if git fails."""
    try:
        done = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=ROOT
        )
        return done.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


class Checks:
    """Collects check results; a crash inside a check becomes a failed check."""

    def __init__(self) -> None:
        """Start with no results."""
        self.items: List[Dict[str, Any]] = []

    def run(self, name: str, check: Callable[[], Result]) -> bool:
        """Run one check and record it."""
        started = time.monotonic()
        try:
            passed, details = check()
        except Exception as exc:  # a failed check must not stop the others
            passed, details = False, f"{type(exc).__name__}: {exc}"
        print(
            f"[{'PASS' if passed else 'FAIL'}] {name} ({time.monotonic() - started:.1f}s)\n       {details}",
            flush=True,
        )
        self.items.append(
            {"name": name, "passed": bool(passed), "details": str(details)}
        )
        return bool(passed)


def check_services() -> Result:
    """Redis Stack (with the search module), the embedding model and the database answer."""
    client = make_binary_redis()
    modules = [
        m[b"name"].decode().lower() if isinstance(m, dict) else str(m)
        for m in client.module_list()
    ]
    if not any("search" in m for m in modules):
        return (
            False,
            f"Redis has no search module (modules: {modules}); use redis/redis-stack-server",
        )
    from hw9.embedder import OllamaEmbedder

    vector = OllamaEmbedder().embed("hello")
    engine = db.make_engine()
    columns = db.get_view_count(engine, 1)
    return len(vector) == config.EMBED_DIM and columns is not None, (
        f"Redis modules {modules}; embedding dim {len(vector)}; view_count column readable"
    )


def check_part1() -> Result:
    """Counter counts 1..12, key starts with the prefix, DB synced at 10."""
    import redis

    client = redis.Redis(
        host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
    )
    cache = ClinicalTrialCache(client)
    trial = db.get_trial_by_code(cache.engine, CODE)
    old_db = db.get_view_count(cache.engine, trial["id"])
    key = cache.views_key(trial["id"])
    old_redis = client.get(key)
    try:
        client.delete(key)
        totals = [cache.increment_clinical_trial_views(trial["id"]) for _ in range(12)]
        synced = db.get_view_count(cache.engine, trial["id"])
    finally:
        client.delete(key)
        if old_redis is not None:
            client.set(key, old_redis)
        db.set_view_count(cache.engine, trial["id"], old_db or 0)
    ok = (
        totals == list(range(1, 13))
        and synced == 10
        and key.startswith(config.PREFIX + ":")
    )
    return (
        ok,
        f"totals {totals[:3]}...{totals[-1]}; database view_count after 12 accesses = {synced}; key {key}",
    )


def check_part2() -> Result:
    """Vector index: exact duplicate ~1.0, unrelated lower."""
    cache = make_cache()
    cache.clear()
    cache.store(
        "What is the participant capacity of trial CT-2026-101?", "A", entity="none"
    )
    exact = cache.lookup("What is the participant capacity of trial CT-2026-101?")
    other = cache.lookup("How do I bake sourdough bread?")
    cache.clear()
    ok = (
        exact is not None
        and exact.similarity >= 0.99
        and other.similarity < exact.similarity
    )
    return (
        ok,
        f"exact duplicate similarity {exact.similarity}; unrelated {other.similarity}",
    )


def check_part3_cases() -> Result:
    """cache_cases.yaml: 40 cases, 10 per type."""
    spec = yaml.safe_load(config.CASES_PATH.read_text(encoding="utf-8"))
    types = [c["type"] for c in spec["cases"]]
    ok = (
        len(types) == 40
        and all(types.count(t) == 10 for t in set(types))
        and len(set(types)) == 4
    )
    return ok, f"{len(types)} cases, types {sorted(set(types))}"


def check_stale() -> Result:
    """A cached answer goes stale after an UPDATE; the version check refreshes it."""
    cache = make_cache()
    cache.clear()
    engine = db.make_engine()
    original = db.get_trial_by_code(engine, CODE)["participant_capacity"]
    q = f"What is the participant capacity of trial {CODE}?"
    agents = HW8Agents(Brain(mode="stub"))
    try:
        first = QAService(cache, agents, engine).answer(q)
        db.update_capacity(engine, CODE, original + 1)
        stale = QAService(cache, agents, engine, check_version=False).answer(q)
        fresh = QAService(cache, agents, engine, check_version=True).answer(q)
        again = QAService(cache, agents, engine, check_version=True).answer(q)
    finally:
        db.update_capacity(engine, CODE, original)
        cache.clear()
    ok = (not first["is_cached"] and stale["is_cached"] and fresh["invalidated"]
          and not fresh["is_cached"] and again["is_cached"])  # fmt: skip
    return (
        ok,
        f"miss -> stale hit -> invalidated refresh -> hit: {[first['is_cached'], stale['is_cached'], fresh['is_cached'], again['is_cached']]}",
    )


def check_part4_files() -> Result:
    """Datasets hold only questions; reference and lessons.json have the required fields."""
    problems = []
    for name, size in (("training", 12), ("validation", 12), ("test", 16)):
        rows = json.loads(
            (config.DATA_DIR / f"{name}_data.json").read_text(encoding="utf-8")
        )
        if len(rows) != size or any(set(r) != {"id", "question"} for r in rows):
            problems.append(f"{name}_data.json")
    reference = json.loads(
        (config.DATA_DIR / "reference_data.json").read_text(encoding="utf-8")
    )
    if not reference.get("entries"):
        problems.append("reference_data.json")
    lessons_path = config.DATA_DIR / "lessons.json"
    if not lessons_path.exists():
        problems.append("lessons.json missing")
    else:
        need = {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"}
        lessons = json.loads(lessons_path.read_text(encoding="utf-8"))
        if not lessons or any(not need <= set(x) for x in lessons):
            problems.append("lessons.json fields")
        if not any(x["status"] == "kept" for x in lessons):
            problems.append("no kept lesson")
    final = config.RAW_DIR / "part4_final.json"
    if (
        not final.exists()
        or len(json.loads(final.read_text(encoding="utf-8"))["table"]) != 4
    ):
        problems.append("part4_final.json (four variants)")
    return not problems, "all present and well-formed" if not problems else "; ".join(
        problems
    )


def check_offline_tests() -> Result:
    """The offline pytest file passes."""
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_hw9_offline.py"],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    lines = [line for line in done.stdout.strip().splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else "no pytest output"


def check_deliverables() -> Result:
    """Evidence files exist."""
    names = ["raw/part1_counter.json", "raw/part2_results.json", "raw/part3_sweep.json",
             "raw/part3_false_hit.json", "raw/part3_stale.json", "raw/part4_revision_demo.json",
             "raw/part4_validation.json", "raw/part4_lesson_reuse.json", "AI_USE.md"]  # fmt: skip
    missing = [n for n in names if not (config.REPORT_DIR / n).exists()]
    if not config.CASES_PATH.exists():
        missing.append("cache_cases.yaml")
    return not missing, "all present" if not missing else "missing: " + ", ".join(
        missing
    )


def main() -> None:
    """Run every check and write verification.json."""
    print(banner("smoke test (make verify-hw09)"))
    checks = Checks()
    checks.run(
        "Redis Stack search module, embedding model and database are reachable",
        check_services,
    )
    checks.run(
        "Part 1: counter counts, uses the s4833: key, syncs to the database every 10",
        check_part1,
    )
    checks.run(
        "Part 2: vector index returns similarity ~1.0 for a duplicate", check_part2
    )
    checks.run(
        "Part 3.1: cache_cases.yaml has 40 labeled cases (10 per type)",
        check_part3_cases,
    )
    checks.run(
        "Part 3.5: stale hit, then invalidation with the data-version marker",
        check_stale,
    )
    checks.run(
        "Part 4: datasets, reference, lessons.json and four-variant results",
        check_part4_files,
    )
    checks.run("Offline unit tests pass", check_offline_tests)
    checks.run("Evidence files present", check_deliverables)
    overall = all(item["passed"] for item in checks.items)
    record = {
        "homework": config.HOMEWORK,
        "sid4": config.SID4,
        "port_base": config.PORT_BASE,
        "prefix": config.PREFIX,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "domain": config.DOMAIN_NAME,
        "model": f"{config.MODEL_NAME} (Ollama) for the agent runs; {config.EMBED_MODEL} embeddings; stub text in this smoke test",
        "commit_hash": git_output("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git_output("status", "--porcelain")),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "overall_pass": overall,
        "checks": checks.items,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    failed = [c["name"] for c in checks.items if not c["passed"]]
    print(f"\nwrote {OUTPUT_PATH}")
    print(banner("smoke test (make verify-hw09)"))
    print("OVERALL: PASS" if overall else f"OVERALL: FAIL ({len(failed)} failed)")
    raise SystemExit(0 if overall else 1)


if __name__ == "__main__":
    main()
