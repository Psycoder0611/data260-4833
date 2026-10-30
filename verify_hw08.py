# ruff: noqa: E501
"""HW8 smoke test. Writes reports/hw08/verification.json.

Needs Kafka running (docker compose -f docker-compose.hw8.yml up -d). It checks
the basics of every part, not every edge case:

  Part 1  topics exist; CREATE then GET round-trip through Kafka; the
          correlation_id comes back unchanged (also on errors); validation and
          unknown-operation errors; the FastAPI wrapper (Kafka and direct routes)
  Part 2  a question goes inbox -> tasks -> drafts -> final with one correlation_id
  Part 3  duplicate replay is skipped; a killed Writer's message is redelivered
          and committed only after success; a poison message is retried, dead-
          lettered and does not block the next message; keyed messages keep
          their order inside one partition
  Other   the offline tests pass; the two JMeter plans are present and valid

The agents in checks 7-11 run with the stub model (fixed text), so the test is
quick and does not depend on what qwen3:8b happens to say. It does not change
application code; it only creates its own test messages and temporary files.

Run:  python verify_hw08.py          (or: make verify-hw08)
      python verify_hw08.py --quick  (skip the offline tests and Part 3 scenarios)
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import requests

from hw8 import config, failure_tests, kafka_io, logs, ordering
from hw8.entity_worker import EntityWorker
from hw8.rpc_client import KafkaRPC, RpcTimeout

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = config.REPORT_DIR / "verification.json"
API = f"http://127.0.0.1:{config.PORT_BASE}"
OFFLINE_TESTS = [
    "test_hw8_part1_offline.py",
    "test_hw8_agents_offline.py",
    "test_hw8_failure_scenarios_offline.py",
    "test_hw8_tools_offline.py",
]
TRIAL = {
    "trialTitle": f"verify-hw08-{config.VERIFY_SEED}",
    "sponsor": "Verify Sponsor",
    "trial_code": f"VERIFY-{config.VERIFY_SEED}",
    "participant_capacity": 50,
    "submitterEmail": "verify@example.org",
    "category": "Cardiology",
}
Result = Tuple[bool, str]


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

    async def run(self, name: str, check: Callable[[], Awaitable[Result]]) -> bool:
        """Run one check and record it."""
        started = time.monotonic()
        try:
            passed, details = await check()
        except Exception as exc:  # a failed check must not stop the others
            passed, details = False, f"{type(exc).__name__}: {exc}"
        mark = "PASS" if passed else "FAIL"
        print(
            f"[{mark}] {name} ({time.monotonic() - started:.1f}s)\n       {details}",
            flush=True,
        )
        self.items.append(
            {"name": name, "passed": bool(passed), "details": str(details)}
        )
        return bool(passed)


# ------------------------------------------------------------------- Part 1
async def check_topics() -> Result:
    """All HW8 topics exist with the right number of partitions."""
    found = await kafka_io.ensure_topics()
    wrong = {
        t: found.get(t) for t, n in config.TOPIC_PARTITIONS.items() if found.get(t) != n
    }
    return (
        not wrong,
        f"partitions {found}" if not wrong else f"wrong partition counts: {wrong}",
    )


class WorkerKeeper:
    """Makes sure some worker answers; starts one in this process if none does."""

    def __init__(self) -> None:
        """No worker started yet."""
        self.task: Optional["asyncio.Task"] = None
        self.note = "existing worker answered"

    async def ensure(self, rpc: KafkaRPC) -> None:
        """Ping with an unknown operation; start a local worker if there is no reply."""
        try:
            await rpc.request("PING", {}, f"verify-ping-{uuid.uuid4()}")
            return
        except RpcTimeout:
            pass
        self.note = "no worker was running, so verify_hw08.py started one"
        self.task = asyncio.create_task(EntityWorker().run())
        await asyncio.sleep(5)
        await rpc.request("PING", {}, f"verify-ping-{uuid.uuid4()}")

    async def stop(self) -> None:
        """Stop the local worker (if any)."""
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass


async def check_round_trip(
    rpc: KafkaRPC, keeper: WorkerKeeper, state: Dict[str, Any]
) -> Result:
    """CREATE then GET over Kafka; the entity comes back and ids are preserved."""
    await keeper.ensure(rpc)
    create_id, get_id = f"verify-create-{uuid.uuid4()}", f"verify-get-{uuid.uuid4()}"
    created = await rpc.request(config.CREATE_OPERATION, TRIAL, create_id)
    if not created.get("success") or created.get("correlation_id") != create_id:
        return False, f"CREATE failed or id changed: {created}"
    entity_id = created.get(config.ID_FIELD)
    got = await rpc.request(config.GET_OPERATION, {config.ID_FIELD: entity_id}, get_id)
    entity = got.get("entity", {})
    same = all(entity.get(k) == v for k, v in TRIAL.items())
    ok = got.get("success") and got.get("correlation_id") == get_id and same
    state["entity_id"] = entity_id
    return bool(
        ok
    ), f"{keeper.note}; created {entity_id}, GET returned it, ids preserved={bool(ok)}"


async def check_errors(rpc: KafkaRPC) -> Result:
    """Unknown operation, unknown id and invalid data give clean errors with the id."""
    outcomes = {}
    for label, op, data, expected in (
        ("unknown operation", "NOPE", {}, "Unknown operation"),
        ("unknown id", config.GET_OPERATION, {config.ID_FIELD: "missing"}, "not found"),
        (
            "invalid data",
            config.CREATE_OPERATION,
            {**TRIAL, "participant_capacity": 0},
            "participant_capacity",
        ),
    ):
        cid = f"verify-err-{uuid.uuid4()}"
        reply = await rpc.request(op, data, cid)
        outcomes[label] = (
            reply.get("success") is False
            and reply.get("correlation_id") == cid
            and expected in str(reply.get("error"))
        )
    return all(outcomes.values()), str(outcomes)


async def check_api(state: Dict[str, Any]) -> Result:
    """The FastAPI wrapper answers on PORT_BASE through Kafka and directly."""
    process: Optional[subprocess.Popen] = None

    def up() -> bool:
        try:
            return requests.get(f"{API}/", timeout=3).status_code == 200
        except requests.RequestException:
            return False

    started_here = False
    if not up():
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "hw8.api:app", "--host", "127.0.0.1",
             "--port", str(config.PORT_BASE)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        started_here = True
        for _ in range(40):
            if up():
                break
            await asyncio.sleep(1)
    try:
        body = {"operation": config.CREATE_OPERATION, "data": TRIAL}
        cid = f"verify-api-{uuid.uuid4()}"
        kafka = requests.post(
            f"{API}/api/hw8/entity",
            json=body,
            headers={"X-Correlation-ID": cid},
            timeout=15,
        ).json()
        direct = requests.post(
            f"{API}/api/hw8/entity-direct", json=body, timeout=10
        ).json()
        ok = (
            kafka.get("success") is True
            and kafka.get("correlation_id") == cid
            and direct.get("success") is True
        )
        where = "started by this script" if started_here else "already running"
        return (
            ok,
            f"API {where} at {API}; Kafka route success={kafka.get('success')}, direct route success={direct.get('success')}",
        )
    finally:
        if process:
            process.terminate()


# ------------------------------------------------------------------- Part 2
async def check_pipeline(state: Dict[str, Any]) -> Result:
    """inbox -> tasks -> drafts -> final with one correlation_id (stub model)."""
    run = uuid.uuid4().hex[:8]
    tmp = tempfile.mkdtemp(prefix="hw8verify_")
    offsets = {t: await kafka_io.end_offsets(t) for t in (
        config.INBOX_TOPIC, config.TASKS_TOPIC, config.DRAFTS_TOPIC, config.FINAL_TOPIC)}  # fmt: skip
    launcher = failure_tests.InProcessLauncher()
    agents = []
    for script, topic_group in (
        ("planner", "planner"),
        ("writer", "writer"),
        ("reviewer", "reviewer"),
    ):
        args = ["--group", f"{config.PREFIX}_verify_{topic_group}_{run}", "--offset-reset", "latest",
                "--llm", "stub", "--state-db", f"{tmp}/{topic_group}.db"]  # fmt: skip
        agents.append(await launcher.launch(script, args, script.upper()))
    try:
        for agent in agents:
            if not await agent.wait_for(failure_tests.READY, 60):
                return False, f"{agent.label} did not become ready"
        cid = f"verify-q-{run}"
        question = {
            "correlation_id": cid,
            "question": "What must a trial listing include?",
        }
        await failure_tests.send(config.INBOX_TOPIC, question, cid)
        deadline = time.monotonic() + 60
        final: Dict[str, Any] = {}
        while time.monotonic() < deadline and not final:
            rows = await kafka_io.read_since(
                config.FINAL_TOPIC, offsets[config.FINAL_TOPIC], 1.0
            )
            final = next(
                (
                    r["value"]
                    for r in rows
                    if isinstance(r["value"], dict)
                    and r["value"].get("correlation_id") == cid
                ),
                {},
            )
        seen = {}
        for topic in offsets:
            rows = await kafka_io.read_since(topic, offsets[topic], 1.0)
            seen[topic] = bool(failure_tests.drafts_for(rows, cid))
        ok = (
            bool(final)
            and final.get("status") == "approved"
            and bool(final.get("answer"))
            and all(seen.values())
        )
        return (
            ok,
            f"final status={final.get('status')}, correlation_id on every topic={seen}",
        )
    finally:
        for agent in agents:
            await agent.stop()


# ------------------------------------------------------------------- Part 3
async def check_duplicate(state: Dict[str, Any]) -> Result:
    """A replayed correlation_id is skipped with idempotency on."""
    with tempfile.TemporaryDirectory(prefix="hw8verify_") as tmp:
        result = await failure_tests.scenario_duplicate(
            failure_tests.InProcessLauncher(), uuid.uuid4().hex[:6], Path(tmp)
        )
    after, before = result["after"], result["before"]
    ok = after["drafts_produced"] == 1 and after["duplicates_skipped"] == 1
    return (
        ok,
        f"with idempotency: {after['drafts_produced']} draft, {after['duplicates_skipped']} duplicate skipped (without: {before['drafts_produced']} drafts)",
    )


async def check_death(state: Dict[str, Any]) -> Result:
    """A Writer stopped mid-work gets the message again; offset commits after success."""
    with tempfile.TemporaryDirectory(prefix="hw8verify_") as tmp:
        result = await failure_tests.scenario_death(
            failure_tests.InProcessLauncher(), uuid.uuid4().hex[:6], Path(tmp),
            victim_ms=3000, redelivery_wait=4.0,
        )  # fmt: skip
    after = result["after"]
    killed = [
        v for v in after["committed_offsets_when_killed"].values() if v is not None
    ]
    final = [v for v in after["final_committed_offsets"].values() if v is not None]
    ok = (
        after["victim_redelivered_after_restart"]
        and after["victim_draft_produced"]
        and max(final) == max(killed) + 1
    )
    return (
        ok,
        f"redelivered={after['victim_redelivered_after_restart']}, draft produced={after['victim_draft_produced']}, offset {max(killed)} -> {max(final)}",
    )


async def check_poison(state: Dict[str, Any]) -> Result:
    """A poison message is retried 3 times, dead-lettered, and the next one flows."""
    with tempfile.TemporaryDirectory(prefix="hw8verify_") as tmp:
        result = await failure_tests.scenario_poison(
            failure_tests.InProcessLauncher(),
            uuid.uuid4().hex[:6],
            Path(tmp),
            observe_seconds=3,
        )
    after = result["after"]
    ok = (
        after["failed_attempts"] == config.MAX_ATTEMPTS
        and len(after["dead_letter_messages"]) == 1
        and after["good_message_processed"]
    )
    return (
        ok,
        f"attempts={after['failed_attempts']}, dead-letter messages={len(after['dead_letter_messages'])}, next message processed={after['good_message_processed']}",
    )


async def check_ordering(state: Dict[str, Any]) -> Result:
    """With the entity as the key, related messages stay in one partition, in order."""
    with tempfile.TemporaryDirectory(prefix="hw8verify_") as tmp:
        result = await failure_tests.scenario_ordering(
            failure_tests.InProcessLauncher(), uuid.uuid4().hex[:6],
            Path(tmp) / "state", Path(tmp) / "raw", work_scale=0.2,
        )  # fmt: skip
    keyed = result["keyed"]["analysis"]
    ok = (
        keyed["messages_processed"] == ordering.MESSAGE_COUNT
        and keyed["total_inversions"] == 0
        and keyed["entities_in_more_than_one_partition"] == 0
    )
    unkeyed = result["unkeyed"]["analysis"]
    return (
        ok,
        f"keyed: {keyed['total_inversions']} inversions, {keyed['entities_in_more_than_one_partition']} entities split; unkeyed: {unkeyed['total_inversions']} inversions, {unkeyed['entities_in_more_than_one_partition']} entities split",
    )


# ------------------------------------------------------------- static checks
async def check_offline_tests() -> Result:
    """The offline pytest files pass."""
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *OFFLINE_TESTS],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    lines = [line for line in done.stdout.strip().splitlines() if line.strip()]
    return done.returncode == 0, lines[-1] if lines else "no pytest output"


async def check_jmeter_plans() -> Result:
    """Both JMeter plans exist and have 100 threads, 10 s ramp-up, loop 1."""
    problems = []
    for name, path in (
        ("kafka_endpoint.jmx", "/api/hw8/entity"),
        ("direct_endpoint.jmx", "/api/hw8/entity-direct"),
    ):
        plan = config.REPORT_DIR / "jmeter" / name
        if not plan.exists():
            problems.append(f"{name} missing")
            continue
        # JMeter rewrites numbers as <intProp> when it saves a plan, so read
        # both kinds of property.
        props = {
            e.get("name"): (e.text or "").strip()
            for tag in ("stringProp", "intProp")
            for e in ET.parse(plan).getroot().iter(tag)
        }
        if (
            props.get("ThreadGroup.num_threads"),
            props.get("ThreadGroup.ramp_time"),
            props.get("LoopController.loops"),
            props.get("HTTPSampler.path"),
        ) != ("100", "10", "1", path):
            problems.append(f"{name} settings differ")
    return (
        not problems,
        "both plans: 100 threads, 10 s ramp-up, 1 loop"
        if not problems
        else "; ".join(problems),
    )


async def check_deliverables() -> Result:
    """The evidence folder has RUN_LOG, METRICS, AI_USE and raw data."""
    names = ["RUN_LOG.txt", "METRICS.md", "AI_USE.md"]
    missing = [n for n in names if not (config.REPORT_DIR / n).exists()]
    raw = list(config.RAW_DIR.glob("*")) if config.RAW_DIR.exists() else []
    if not raw:
        missing.append("raw/ (empty)")
    return not missing, "all present" if not missing else "missing: " + ", ".join(
        missing
    )


# ---------------------------------------------------------------------- main
async def run_all(quick: bool, skip_api: bool) -> Dict[str, Any]:
    """Run every check and return the verification record."""
    checks = Checks()
    state: Dict[str, Any] = {}
    keeper = WorkerKeeper()
    await checks.run(
        "Kafka is up and the 7 HW8 topics have the right partitions", check_topics
    )
    rpc = KafkaRPC(component="VERIFY", verbose=False, timeout=8)
    await rpc.start()
    try:
        await checks.run(
            "CREATE then GET round-trip through Kafka (worker, correlation_id kept)",
            lambda: check_round_trip(rpc, keeper, state),
        )
        await checks.run(
            "Errors are clean and carry the original correlation_id",
            lambda: check_errors(rpc),
        )
    finally:
        await rpc.stop()
    if not skip_api:
        await checks.run(
            "FastAPI wrapper on PORT_BASE: Kafka route and direct route",
            lambda: check_api(state),
        )
    await keeper.stop()
    await checks.run(
        "Pipeline: one question reaches s4833_final with the same correlation_id",
        lambda: check_pipeline(state),
    )
    if not quick:
        await checks.run(
            "Duplicate delivery: replayed correlation_id is skipped",
            lambda: check_duplicate(state),
        )
        await checks.run(
            "Consumer death: message redelivered, offset committed only after success",
            lambda: check_death(state),
        )
        await checks.run(
            "Poison message: bounded retries, dead-letter topic, next message flows",
            lambda: check_poison(state),
        )
        await checks.run(
            "Ordering: entity key keeps related messages in one partition, in order",
            lambda: check_ordering(state),
        )
        await checks.run("Offline unit tests pass", check_offline_tests)
    await checks.run(
        "JMeter plans present (100 threads, ramp 10, loop 1)", check_jmeter_plans
    )
    await checks.run(
        "Evidence files present (RUN_LOG, METRICS, AI_USE, raw/)", check_deliverables
    )
    overall = all(item["passed"] for item in checks.items)
    return {
        "homework": config.HOMEWORK,
        "sid4": config.SID4,
        "port_base": config.PORT_BASE,
        "prefix": config.PREFIX,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "domain": config.DOMAIN_NAME,
        "model": f"{config.MODEL_NAME} (Ollama) for the pipeline runs; stub text in this smoke test",
        "commit_hash": git_output("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git_output("status", "--porcelain")),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "quick_mode": quick,
        "overall_pass": overall,
        "checks": checks.items,
    }


def main() -> None:
    """Parse arguments, run the checks and write verification.json."""
    parser = argparse.ArgumentParser(description="HW8 smoke test")
    parser.add_argument(
        "--quick", action="store_true", help="skip Part 3 scenarios and offline tests"
    )
    parser.add_argument(
        "--skip-api", action="store_true", help="do not call the FastAPI wrapper"
    )
    args = parser.parse_args()
    print(logs.banner("smoke test (make verify-hw08)"))
    record = asyncio.run(run_all(args.quick, args.skip_api))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    failed = [c["name"] for c in record["checks"] if not c["passed"]]
    print(f"\nwrote {OUTPUT_PATH}")
    print(logs.banner("smoke test (make verify-hw08)"))
    print(
        "OVERALL: PASS"
        if record["overall_pass"]
        else f"OVERALL: FAIL ({len(failed)} failed)"
    )
    raise SystemExit(0 if record["overall_pass"] else 1)


if __name__ == "__main__":
    main()
