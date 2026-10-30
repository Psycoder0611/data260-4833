"""Part 3 failure scenarios: duplicate delivery, consumer death, poison message, order.

Each scenario runs a "before" case (the fix switched off) and an "after" case
(the fix on) with the same Writer code, sends real messages through Kafka and
returns the evidence as a dict. The Writer runs as a separate process
(SubprocessLauncher) for the reported runs; the offline tests run it in the same
process (InProcessLauncher) against the fake broker.
"""

import asyncio
import csv
import importlib
import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Union

from hw8 import config, kafka_io, ordering
from hw8.logs import get_logger, read_jsonl

READY = r"Consumer is ready and listening"
PARTITIONS = re.compile(r"partitions=\[([0-9, ]*)\]")
ROOT = Path(__file__).resolve().parent.parent
log = get_logger("TEST")


# --------------------------------------------------------------------- agents
class AgentHandle:
    """A running agent: its log lines, and ways to wait for, kill or stop it."""

    def __init__(self, label: str) -> None:
        """Start with no log lines."""
        self.label = label
        self.lines: List[str] = []

    async def wait_for(
        self, pattern: Union[str, Pattern[str]], timeout: float, since: int = 0
    ) -> Optional["re.Match[str]"]:
        """Wait for a log line matching pattern (searching from line `since`)."""
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        deadline = time.monotonic() + timeout
        while True:
            for line in self.lines[since:]:
                found = regex.search(line)
                if found:
                    return found
            if time.monotonic() > deadline or not self.alive():
                return None
            await asyncio.sleep(0.05)

    async def wait_for_in_order(
        self, patterns: List[str], timeout: float, since: int = 0
    ) -> bool:
        """Wait until the patterns have each appeared, one after the other."""
        deadline = time.monotonic() + timeout
        position = since
        for pattern in patterns:
            regex = re.compile(pattern)
            while True:
                hit = next(
                    (
                        i
                        for i in range(position, len(self.lines))
                        if regex.search(self.lines[i])
                    ),
                    None,
                )
                if hit is not None:
                    position = hit + 1
                    break
                if time.monotonic() > deadline or not self.alive():
                    return False
                await asyncio.sleep(0.05)
        return True

    def count(self, pattern: str, since: int = 0) -> int:
        """Number of log lines (from `since`) that match pattern."""
        regex = re.compile(pattern)
        return sum(1 for line in self.lines[since:] if regex.search(line))

    def partitions(self) -> Optional[List[int]]:
        """Partitions from the most recent ready / ASSIGNMENT line."""
        for line in reversed(self.lines):
            if READY in line or "ASSIGNMENT CHANGED" in line:
                found = PARTITIONS.search(line)
                if found:
                    text = found.group(1).strip()
                    return [int(p) for p in text.split(",")] if text else []
        return None

    def alive(self) -> bool:
        """True while the agent is running."""
        raise NotImplementedError

    async def kill(self) -> None:
        """Stop the agent abruptly (SIGKILL), with no clean shutdown."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Stop the agent cleanly (it leaves its consumer group)."""
        raise NotImplementedError


class SubprocessAgent(AgentHandle):
    """An agent started with ``python <script>.py ...`` as its own process."""

    def __init__(self, label: str, process: "asyncio.subprocess.Process") -> None:
        """Start reading the process output."""
        super().__init__(label)
        self.process = process
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        """Copy the process output to the console and to self.lines."""
        assert self.process.stdout is not None
        async for raw in self.process.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            self.lines.append(line)
            print(f"    | {line}", flush=True)

    def alive(self) -> bool:
        """True while the process has not exited."""
        return self.process.returncode is None

    async def kill(self) -> None:
        """SIGKILL the process."""
        if self.alive():
            self.process.send_signal(signal.SIGKILL)
        await self.process.wait()
        await asyncio.sleep(0.2)

    async def stop(self) -> None:
        """SIGTERM, then SIGKILL if it does not exit within 20 seconds."""
        if self.alive():
            self.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self.process.wait(), timeout=20)
            except asyncio.TimeoutError:
                await self.kill()
        await asyncio.sleep(0.2)


class InProcessAgent(AgentHandle):
    """An agent run as a task in this process (offline tests only)."""

    def __init__(self, label: str, runner: Any) -> None:
        """Capture the runner's log lines and start it."""
        super().__init__(label)
        self.runner = runner
        self.error: Optional[BaseException] = None
        handler = logging.Handler()
        self.handler = handler
        handler.emit = (
            lambda record: self.lines.append(  # type: ignore[method-assign]
                f"{datetime.fromtimestamp(record.created):%H:%M:%S.%f}"[:-3]
                + f" [{record.name}] {record.getMessage()}"
            )
        )
        runner.log.addHandler(handler)
        self.task = asyncio.create_task(runner.run())
        self.task.add_done_callback(self._finished)

    def _finished(self, task: "asyncio.Task") -> None:
        """Remember how the task ended."""
        if not task.cancelled():
            self.error = task.exception()

    def alive(self) -> bool:
        """True until the task ends."""
        return not self.task.done()

    async def kill(self) -> None:
        """Cancel the task."""
        self.runner.log.removeHandler(self.handler)
        self.task.cancel()
        try:
            await self.task
        except (asyncio.CancelledError, Exception):
            pass

    async def stop(self) -> None:
        """Same as kill() for the in-process variant."""
        await self.kill()


class SubprocessLauncher:
    """Starts agents as separate processes."""

    async def launch(self, script: str, args: List[str], label: str) -> AgentHandle:
        """Start ``python <script>.py <args>`` and return its handle."""
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        print(f"  $ python {script}.py {' '.join(args)}", flush=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ROOT / f"{script}.py"),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
        )
        return SubprocessAgent(label, process)


class InProcessLauncher:
    """Runs agents inside this process (for the offline tests)."""

    async def launch(self, script: str, args: List[str], label: str) -> AgentHandle:
        """Build the agent's runner from its script and start it as a task."""
        sys.path.insert(0, str(ROOT))
        module = importlib.import_module(script)
        return InProcessAgent(label, module.build_runner(args))


# -------------------------------------------------------------------- helpers
def heading(text: str) -> None:
    """Print a section heading."""
    print(f"\n--- {text} ---", flush=True)


def task_message(cid: str, run_id: str, **extra: Any) -> Dict[str, Any]:
    """A valid message for s4833_tasks (what the Planner would have sent)."""
    return {
        "correlation_id": cid,
        "stage": "plan",
        "question": f"failure test {cid}",
        "plan": ["Read the listing", "Check the rules", "Write the answer"],
        "test_run": run_id,
        **extra,
    }


async def send(topic: str, message: Dict[str, Any], key: Optional[str]) -> Any:
    """Publish one message and return its Kafka metadata."""
    producer = kafka_io.make_producer()
    await producer.start()
    try:
        return await producer.send_and_wait(
            topic, kafka_io.dumps(message), key=key.encode("utf-8") if key else None
        )
    finally:
        await producer.stop()


def say_sent(what: str, meta: Any, cid: Optional[str]) -> None:
    """Log a message that the test itself published."""
    log.info(
        "%s -> topic=%s partition=%d offset=%d correlation_id=%s",
        what,
        meta.topic,
        meta.partition,
        meta.offset,
        cid,
    )


def common_args(group: str, db: Path, extra: List[str]) -> List[str]:
    """Arguments every test Writer gets (fresh group, stub model, own state file)."""
    return [
        "--instance", "A",
        "--group", group,
        "--offset-reset", "latest",
        "--llm", "stub",
        "--state-db", str(db),
        *extra,
    ]  # fmt: skip


def excerpt(agent: AgentHandle, start: int = 0, limit: int = 40) -> List[str]:
    """The agent's log lines from `start` (at most `limit`)."""
    return agent.lines[start : start + limit]


def drafts_for(rows: List[Dict[str, Any]], cid: str) -> List[Dict[str, Any]]:
    """Messages in rows whose value has this correlation_id."""
    return [
        r
        for r in rows
        if isinstance(r["value"], dict) and r["value"].get("correlation_id") == cid
    ]


# ------------------------------------------------------------------ duplicate
async def scenario_duplicate(
    launcher: Any, run_id: str, state_dir: Path
) -> Dict[str, Any]:
    """Replay a message with the same correlation_id, without and with idempotency."""
    results: Dict[str, Any] = {}
    for mode, extra in (("before", ["--no-idempotency"]), ("after", [])):
        heading(f"Duplicate delivery - {mode.upper()} the fix")
        cid = f"dup-{mode}-{run_id}"
        group = f"{config.PREFIX}_t3_dup_{mode}_{run_id}"
        drafts_start = await kafka_io.end_offsets(config.DRAFTS_TOPIC)
        writer = await launcher.launch(
            "writer",
            common_args(group, state_dir / f"dup_{mode}_{run_id}.db", extra),
            "WRITER-A",
        )
        if not await writer.wait_for(READY, 120):
            raise RuntimeError("Writer did not become ready")
        message = task_message(cid, run_id)
        mark = len(writer.lines)
        say_sent("original sent", await send(config.TASKS_TOPIC, message, cid), cid)
        await writer.wait_for(r"COMMITTED", 60, since=mark)
        mark = len(writer.lines)
        meta = await send(config.TASKS_TOPIC, message, cid)
        say_sent("REPLAY of the same message sent", meta, cid)
        await writer.wait_for(r"COMMITTED", 60, since=mark)
        await asyncio.sleep(1.0)
        rows = await kafka_io.read_since(config.DRAFTS_TOPIC, drafts_start, 2.0)
        drafts = drafts_for(rows, cid)
        skipped = writer.count(r"DUPLICATE correlation_id")
        log.info(
            "RESULT %s: messages sent=2, drafts produced=%d, duplicates skipped=%d",
            mode,
            len(drafts),
            skipped,
        )
        results[mode] = {
            "fix": "idempotency on" if mode == "after" else "idempotency off",
            "correlation_id": cid,
            "messages_sent_to_tasks": 2,
            "drafts_produced": len(drafts),
            "duplicates_skipped": skipped,
            "draft_offsets": [d["offset"] for d in drafts],
            "writer_log": excerpt(writer),
        }
        await writer.stop()
    return results


# ---------------------------------------------------------------- consumer death
async def scenario_death(
    launcher: Any,
    run_id: str,
    state_dir: Path,
    victim_ms: int = 8000,
    redelivery_wait: float = 12.0,
) -> Dict[str, Any]:
    """Kill the Writer mid-processing and restart it, commit-on-receive vs after."""
    results: Dict[str, Any] = {}
    for mode, commit_mode in (("before", "on_receive"), ("after", "after")):
        heading(f"Consumer killed mid-work - {mode.upper()} the fix ({commit_mode})")
        group = f"{config.PREFIX}_t3_death_{mode}_{run_id}"
        key = f"death-{mode}-{run_id}"
        args = common_args(
            group,
            state_dir / f"death_{mode}_{run_id}.db",
            ["--commit-mode", commit_mode],
        )
        drafts_start = await kafka_io.end_offsets(config.DRAFTS_TOPIC)
        writer = await launcher.launch("writer", args, "WRITER-A")
        if not await writer.wait_for(READY, 120):
            raise RuntimeError("Writer did not become ready")
        warm = f"warmup-{mode}-{run_id}"
        mark = len(writer.lines)
        say_sent(
            "warm-up sent",
            await send(config.TASKS_TOPIC, task_message(warm, run_id, work_ms=0), key),
            warm,
        )
        await writer.wait_for(r"COMMITTED", 60, since=mark)
        victim = f"victim-{mode}-{run_id}"
        mark = len(writer.lines)
        meta = await send(
            config.TASKS_TOPIC, task_message(victim, run_id, work_ms=victim_ms), key
        )
        say_sent("victim sent", meta, victim)
        await writer.wait_for(rf"PROCESSING correlation_id={victim}", 60, since=mark)
        await asyncio.sleep(min(1.0, victim_ms / 4000))
        before_kill = await kafka_io.committed_offsets(group, config.TASKS_TOPIC)
        log.info(
            "KILLING the Writer with SIGKILL while it is processing %s; committed "
            "offsets at that moment: %s",
            victim,
            before_kill,
        )
        killed_at = len(writer.lines)
        await writer.kill()
        mid = await kafka_io.read_since(config.DRAFTS_TOPIC, drafts_start, 1.0)
        log.info(
            "drafts produced before the restart: %s",
            [r["value"]["correlation_id"] for r in mid if isinstance(r["value"], dict)],
        )
        log.info("RESTARTING the Writer (same group)")
        again = await launcher.launch("writer", args, "WRITER-A")
        if not await again.wait_for(READY, 120):
            raise RuntimeError("restarted Writer did not become ready")
        wait = victim_ms / 1000 + 25 if mode == "after" else redelivery_wait
        # `again` is a fresh handle, so search all of its lines: the redelivered
        # message can be logged in the same instant as the "ready" line.
        redelivered = await again.wait_for(rf"RECEIVED .*correlation_id={victim}", wait)
        if redelivered and mode == "after":
            await again.wait_for_in_order(
                [rf"SENT .*correlation_id={victim}", r"COMMITTED"],
                victim_ms / 1000 + 60,
            )
        await asyncio.sleep(1.0)
        after = await kafka_io.read_since(config.DRAFTS_TOPIC, drafts_start, 2.0)
        produced = [
            r["value"]["correlation_id"] for r in after if isinstance(r["value"], dict)
        ]
        final_offsets = await kafka_io.committed_offsets(group, config.TASKS_TOPIC)
        log.info(
            "RESULT %s: victim redelivered after restart=%s, drafts now=%s, "
            "final committed offsets=%s",
            mode,
            bool(redelivered),
            produced,
            final_offsets,
        )
        results[mode] = {
            "commit_mode": commit_mode,
            "victim": victim,
            "victim_work_ms": victim_ms,
            "committed_offsets_when_killed": before_kill,
            "victim_redelivered_after_restart": bool(redelivered),
            "drafts_after_restart": produced,
            "victim_draft_produced": victim in produced,
            "final_committed_offsets": final_offsets,
            "writer_log_before_kill": excerpt(writer, 0, killed_at),
            "writer_log_after_restart": excerpt(again, 0, 40),
        }
        await again.stop()
    return results


# --------------------------------------------------------------- poison message
async def scenario_poison(
    launcher: Any, run_id: str, state_dir: Path, observe_seconds: float = 12.0
) -> Dict[str, Any]:
    """A malformed message with a good message behind it, before and after the fix."""
    results: Dict[str, Any] = {}
    for mode, extra in (
        ("before", ["--max-attempts", "0", "--no-dead-letter"]),
        ("after", []),
    ):
        heading(f"Poison message - {mode.upper()} the fix")
        group = f"{config.PREFIX}_t3_poison_{mode}_{run_id}"
        key = f"poison-{mode}-{run_id}"
        args = common_args(group, state_dir / f"poison_{mode}_{run_id}.db", extra)
        drafts_start = await kafka_io.end_offsets(config.DRAFTS_TOPIC)
        dead_start = await kafka_io.end_offsets(config.DEAD_LETTER_TOPIC)
        writer = await launcher.launch("writer", args, "WRITER-A")
        if not await writer.wait_for(READY, 120):
            raise RuntimeError("Writer did not become ready")
        warm = f"warmup-{mode}-{run_id}"
        mark = len(writer.lines)
        await send(config.TASKS_TOPIC, task_message(warm, run_id), key)
        await writer.wait_for(r"COMMITTED", 60, since=mark)
        bad = f"poison-{mode}-{run_id}"
        good = f"after-poison-{mode}-{run_id}"
        bad_message = task_message(bad, run_id)
        bad_message["plan"] = 12345  # not a list of steps: the Writer cannot handle it
        mark = len(writer.lines)
        say_sent(
            "poison message sent", await send(config.TASKS_TOPIC, bad_message, key), bad
        )
        say_sent(
            "good message sent behind it",
            await send(config.TASKS_TOPIC, task_message(good, run_id), key),
            good,
        )
        if mode == "after":
            await writer.wait_for_in_order(
                [
                    r"DEAD LETTER after",
                    r"COMMITTED .*after dead-lettering",
                    rf"SENT .*correlation_id={good}",
                    r"COMMITTED",
                ],
                60,
                since=mark,
            )
        else:
            await asyncio.sleep(observe_seconds)
        await asyncio.sleep(1.0)
        await writer.stop()  # stop first so the attempt count matches the log
        attempts = writer.count(rf"FAILED correlation_id={bad}", since=mark)
        offsets = await kafka_io.committed_offsets(group, config.TASKS_TOPIC)
        drafts = await kafka_io.read_since(config.DRAFTS_TOPIC, drafts_start, 2.0)
        dead = await kafka_io.read_since(config.DEAD_LETTER_TOPIC, dead_start, 2.0)
        good_done = bool(drafts_for(drafts, good))
        log.info(
            "RESULT %s: failed attempts=%d, dead-letter messages=%d, good message "
            "processed=%s, committed offsets=%s",
            mode,
            attempts,
            len(drafts_for(dead, bad)),
            good_done,
            offsets,
        )
        results[mode] = {
            "max_attempts": 0 if mode == "before" else config.MAX_ATTEMPTS,
            "dead_letter": mode == "after",
            "poison": bad,
            "good_message": good,
            "failed_attempts": attempts,
            "dead_letter_messages": [d["value"] for d in drafts_for(dead, bad)],
            "good_message_processed": good_done,
            "committed_offsets": offsets,
            "writer_log": excerpt(writer, mark - 1, 60),
        }
    return results


# ---------------------------------------------------------------------- ordering
async def scenario_ordering(
    launcher: Any,
    run_id: str,
    state_dir: Path,
    raw_dir: Path,
    work_scale: float = 1.0,
) -> Dict[str, Any]:
    """Send the 20 VERIFY_SEED messages to two Writers: no key, then entity key."""
    results: Dict[str, Any] = {}
    for mode in ("unkeyed", "keyed"):
        heading(
            f"Ordering - {'WITHOUT' if mode == 'unkeyed' else 'WITH'} a message key"
        )
        tag = f"ord-{mode}-{run_id}"
        group = f"{config.PREFIX}_t3_order_{mode}_{run_id}"
        record = raw_dir / f"part3_ordering_{mode}_processed.jsonl"
        if record.exists():
            record.unlink()
        writers = []
        for instance in ("A", "B"):
            args = common_args(group, state_dir / f"order_{mode}_{run_id}.db", [])
            args[1] = instance
            args += ["--record-path", str(record)]
            writers.append(await launcher.launch("writer", args, f"WRITER-{instance}"))
        for w in writers:
            if not await w.wait_for(READY, 120):
                raise RuntimeError("Writer did not become ready")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            mine = [w.partitions() for w in writers]
            if all(p is not None for p in mine) and sorted(
                sum(mine, [])  # type: ignore[arg-type]
            ) == [0, 1]:
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError("the two Writers did not split the partitions")
        log.info(
            "Writer-A has partitions %s, Writer-B has partitions %s (same group %s)",
            writers[0].partitions(),
            writers[1].partitions(),
            group,
        )
        sent_rows = []
        for message in ordering.generate_messages(tag, work_scale=work_scale):
            key = message["entity"] if mode == "keyed" else None
            meta = await send(config.TASKS_TOPIC, message, key)
            sent_rows.append(
                {
                    "index": message["index"],
                    "correlation_id": message["correlation_id"],
                    "entity": message["entity"],
                    "seq": message["seq"],
                    "key": key or "",
                    "partition": meta.partition,
                    "offset": meta.offset,
                    "work_ms": message["work_ms"],
                }
            )
            log.info(
                "SENT #%02d entity=%s seq=%d key=%s -> partition=%d offset=%d",
                message["index"],
                message["entity"],
                message["seq"],
                key,
                meta.partition,
                meta.offset,
            )
        deadline = time.monotonic() + 180
        while len(read_jsonl(record)) < ordering.MESSAGE_COUNT:
            if time.monotonic() > deadline:
                raise RuntimeError("the Writers did not finish all 20 messages")
            await asyncio.sleep(0.5)
        rows = read_jsonl(record)
        for w in writers:
            await w.stop()
        analysis = ordering.analyze(rows)
        write_ordering_csvs(raw_dir, mode, sent_rows, rows)
        print_ordering_table(mode, analysis, rows)
        results[mode] = {"analysis": analysis, "sent": sent_rows}
    return results


def write_ordering_csvs(
    raw_dir: Path,
    mode: str,
    sent: List[Dict[str, Any]],
    processed: List[Dict[str, Any]],
) -> None:
    """Save the sent order and the processed order as CSV files."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    with open(raw_dir / f"part3_ordering_{mode}_sent.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sent[0]))
        writer.writeheader()
        writer.writerows(sent)
    ranked = sorted(processed, key=lambda r: r["finished"])
    with open(
        raw_dir / f"part3_ordering_{mode}_processed.csv", "w", newline=""
    ) as handle:
        fields = [
            "order",
            "finished_at",
            "instance",
            "partition",
            "offset",
            "entity",
            "seq",
            "correlation_id",
        ]
        out = csv.DictWriter(handle, fieldnames=fields)
        out.writeheader()
        for number, row in enumerate(ranked, start=1):
            out.writerow(
                {
                    "order": number,
                    "finished_at": datetime.fromtimestamp(row["finished"]).isoformat(
                        timespec="milliseconds"
                    ),
                    "instance": row["instance"],
                    "partition": row["partition"],
                    "offset": row["offset"],
                    "entity": row["entity"],
                    "seq": row["seq"],
                    "correlation_id": row["correlation_id"],
                }
            )


def print_ordering_table(
    mode: str, analysis: Dict[str, Any], rows: List[Dict[str, Any]]
) -> None:
    """Print the processing order and the per-entity verdict."""
    print(f"\n  Processing order ({mode}): finish order -> writer/partition entity#seq")
    for number, row in enumerate(sorted(rows, key=lambda r: r["finished"]), start=1):
        print(
            f"   {number:2d}. writer {row['instance']} partition {row['partition']} "
            f"{row['entity']} #{row['seq']}",
            flush=True,
        )
    print(f"\n  Per-entity result ({mode}):")
    for entity, info in analysis["entities"].items():
        verdict = "in order" if info["in_order"] else "OUT OF ORDER"
        print(
            f"   {entity}: partitions {info['partitions']} writers {info['instances']} "
            f"processed seq {info['processed_order']} -> {verdict}",
            flush=True,
        )
    print(
        f"  TOTAL ({mode}): entities out of order={analysis['entities_out_of_order']}, "
        f"entities spread over both partitions="
        f"{analysis['entities_in_more_than_one_partition']}, "
        f"order inversions={analysis['total_inversions']}",
        flush=True,
    )


def save_json(path: Path, data: Any) -> None:
    """Write data as pretty JSON, creating folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
