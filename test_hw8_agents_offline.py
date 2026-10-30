# ruff: noqa: E501
"""Offline tests for HW8 Parts 2 and 3 (pipeline, idempotency, offsets, DLQ, order).

Uses the in-memory broker in hw8/fake_kafka.py and the stub Brain, so no Docker
and no Ollama are needed.  Run:  pytest -q test_hw8_agents_offline.py
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

import pytest

from hw8 import config, fake_kafka, kafka_io, ordering
from hw8.agent_base import AgentOptions, AgentRunner, RetriesExhausted
from hw8.pipeline import Brain, make_planner, make_reviewer, make_writer


# ------------------------------------------------------------------ helpers
async def wait_until(
    check: Callable[[], bool], timeout: float = 5.0, step: float = 0.02
) -> None:
    """Poll until check() is true or fail the test."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not check():
        if loop.time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(step)


def options(
    name: str, in_topic: str, out_topic: Optional[str], **extra: Any
) -> AgentOptions:
    """AgentOptions with test defaults (in-memory idempotency, tiny back-off)."""
    base: Dict[str, Any] = {
        "name": name,
        "in_topic": in_topic,
        "out_topic": out_topic,
        "group_id": f"test_{name}",
        "backoff": 0.0,
        "store_path": ":memory:",
    }
    base.update(extra)
    return AgentOptions(**base)


class Running:
    """A started AgentRunner running as a task (so tests can 'kill' it)."""

    def __init__(self, runner: AgentRunner) -> None:
        """Wrap a runner."""
        self.runner = runner
        self.task = asyncio.create_task(runner.run())
        self.error: Optional[BaseException] = None
        self.task.add_done_callback(self._done)

    def _done(self, task: "asyncio.Task") -> None:
        """Remember an error so tests can look at it."""
        if not task.cancelled():
            self.error = task.exception()

    async def ready(self) -> "Running":
        """Wait until the runner reports its partitions."""
        await wait_until(lambda: bool(self.runner.assigned) or self.task.done())
        return self

    async def kill(self) -> None:
        """Stop the runner abruptly (like killing the process mid-work)."""
        self.task.cancel()
        try:
            await self.task
        except (asyncio.CancelledError, Exception):
            pass


async def start(runner: AgentRunner) -> Running:
    """Start a runner and wait until it is ready."""
    return await Running(runner).ready()


async def send(topic: str, message: Dict[str, Any], key: Optional[str] = None) -> None:
    """Publish one JSON message."""
    producer = kafka_io.make_producer()
    await producer.start()
    await producer.send_and_wait(
        topic, kafka_io.dumps(message), key=key.encode() if key else None
    )
    await producer.stop()


def messages_on(broker: fake_kafka.FakeBroker, topic: str) -> List[Dict[str, Any]]:
    """Every decoded message on a topic, all partitions."""
    out = []
    for log in broker.logs.get(topic, []):
        out.extend(json.loads(r.value) for r in log)
    return out


def plan_message(cid: str, **extra: Any) -> Dict[str, Any]:
    """A valid task message for the Writer."""
    return {
        "correlation_id": cid,
        "stage": "plan",
        "question": f"question {cid}",
        "plan": ["a", "b", "c"],
        "test_run": "t",
        **extra,
    }


def committed(
    broker: fake_kafka.FakeBroker, group: str, topic: str, part: int = 0
) -> Any:
    """Committed offset of a group (None if nothing committed)."""
    return broker.committed.get((group, topic, part))


@pytest.fixture()
def broker(monkeypatch: Any) -> fake_kafka.FakeBroker:
    """A fresh in-memory broker wired into hw8.kafka_io."""
    fake = fake_kafka.FakeBroker(seed=3)
    fake_kafka.install(monkeypatch, fake)
    return fake


# ------------------------------------------------------------ Part 2 pipeline
def test_full_pipeline_keeps_the_correlation_id_through_every_topic(
    broker: Any,
) -> None:
    """inbox -> tasks -> drafts -> final, same correlation_id, status + answer."""

    async def run() -> None:
        brain = Brain("stub")
        runners = [
            await start(
                AgentRunner(
                    options("planner", config.INBOX_TOPIC, config.TASKS_TOPIC),
                    make_planner(brain),
                )
            ),
            await start(
                AgentRunner(
                    options("writer", config.TASKS_TOPIC, config.DRAFTS_TOPIC),
                    make_writer(brain),
                )
            ),
            await start(
                AgentRunner(
                    options("reviewer", config.DRAFTS_TOPIC, config.FINAL_TOPIC),
                    make_reviewer(brain),
                )
            ),
        ]
        await send(
            config.INBOX_TOPIC,
            {"correlation_id": "q-1", "question": "Who can edit a listing?"},
            "q-1",
        )
        await wait_until(lambda: bool(messages_on(broker, config.FINAL_TOPIC)))
        for topic in (
            config.INBOX_TOPIC,
            config.TASKS_TOPIC,
            config.DRAFTS_TOPIC,
            config.FINAL_TOPIC,
        ):
            assert [m["correlation_id"] for m in messages_on(broker, topic)] == ["q-1"]
        final = messages_on(broker, config.FINAL_TOPIC)[0]
        assert final["status"] == "approved"
        assert "Draft answer" in final["answer"]
        assert messages_on(broker, config.TASKS_TOPIC)[0]["plan"]
        for runner in runners:
            await runner.kill()

    asyncio.run(run())


def test_reviewer_rejects_a_low_score_and_skips_test_traffic(broker: Any) -> None:
    """A low review score gives status rejected; test_run messages are not reviewed."""

    class Harsh(Brain):
        def review(self, payload: Dict[str, Any], draft: str) -> Dict[str, Any]:
            return {"score": 3, "feedback": "Too vague."}

    async def run() -> None:
        reviewer = await start(
            AgentRunner(
                options("reviewer", config.DRAFTS_TOPIC, config.FINAL_TOPIC),
                make_reviewer(Harsh("stub")),
            )
        )
        await send(
            config.DRAFTS_TOPIC,
            {"correlation_id": "d-1", "question": "q", "draft": "text"},
        )
        await send(
            config.DRAFTS_TOPIC,
            {
                "correlation_id": "d-2",
                "question": "q",
                "draft": "text",
                "test_run": "x",
            },
        )
        await wait_until(
            lambda: committed(broker, "test_reviewer", config.DRAFTS_TOPIC) == 2
        )
        finals = messages_on(broker, config.FINAL_TOPIC)
        assert [(f["correlation_id"], f["status"]) for f in finals] == [
            ("d-1", "rejected")
        ]
        await reviewer.kill()

    asyncio.run(run())


def test_real_model_replies_are_validated() -> None:
    """The planner/reviewer parsers reject malformed model output."""
    from hw8.pipeline import extract_json

    assert extract_json('noise {"steps": ["a"]} tail') == {"steps": ["a"]}
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(ValueError):
        extract_json("{broken")

    class Chatty(Brain):
        def _ask(self, system: str, user: str) -> str:
            return '{"steps": ["only one"]}'

    with pytest.raises(ValueError):
        Chatty("ollama").plan({"question": "q"})

    class BadScore(Brain):
        def _ask(self, system: str, user: str) -> str:
            return '{"score": 11, "feedback": "x"}'

    with pytest.raises(ValueError):
        BadScore("ollama").review({"question": "q"}, "draft")


# ------------------------------------------------------- Part 3: duplicate
def test_duplicate_delivery_idempotency_on_and_off(broker: Any) -> None:
    """Replaying a correlation_id makes a 2nd draft without the fix, none with it."""

    async def run(idempotent: bool, cid: str) -> int:
        writer = await start(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=f"g_{cid}",
                    idempotent=idempotent,
                    offset_reset="latest",
                ),
                make_writer(Brain("stub")),
            )
        )
        await send(config.TASKS_TOPIC, plan_message(cid), cid)
        await send(config.TASKS_TOPIC, plan_message(cid), cid)  # the replay
        part = broker_partition(cid)
        target = len(broker.logs[config.TASKS_TOPIC][part])  # both sends are in
        await wait_until(
            lambda: committed(broker, f"g_{cid}", config.TASKS_TOPIC, part) == target
        )
        await writer.kill()
        return sum(
            1
            for m in messages_on(broker, config.DRAFTS_TOPIC)
            if m["correlation_id"] == cid
        )

    def broker_partition(cid: str) -> int:
        return ordering.key_partition(cid)

    before = asyncio.run(run(False, "dup-before"))
    after = asyncio.run(run(True, "dup-after"))
    assert before == 2  # the bug: the replay caused a second draft
    assert after == 1  # the fix: the replay was skipped


def test_idempotency_survives_a_restart(broker: Any, tmp_path: Any) -> None:
    """The done-record is on disk, so a restarted agent still skips the replay."""
    db = str(tmp_path / "idem.db")

    async def run() -> None:
        opts = dict(group_id="g_restart", store_path=db, offset_reset="latest")
        first = await start(
            AgentRunner(
                options("writer", config.TASKS_TOPIC, config.DRAFTS_TOPIC, **opts),
                make_writer(Brain("stub")),
            )
        )
        await send(config.TASKS_TOPIC, plan_message("r-1"), "r-1")
        part = ordering.key_partition("r-1")
        await wait_until(
            lambda: committed(broker, "g_restart", config.TASKS_TOPIC, part) == 1
        )
        await first.kill()
        second = await start(
            AgentRunner(
                options("writer", config.TASKS_TOPIC, config.DRAFTS_TOPIC, **opts),
                make_writer(Brain("stub")),
            )
        )
        await send(config.TASKS_TOPIC, plan_message("r-1"), "r-1")
        await wait_until(
            lambda: committed(broker, "g_restart", config.TASKS_TOPIC, part) == 2
        )
        await second.kill()
        assert len(messages_on(broker, config.DRAFTS_TOPIC)) == 1

    asyncio.run(run())


# ------------------------------------------------- Part 3: consumer death
def _death_scenario(broker: Any, commit_mode: str) -> Dict[str, Any]:
    """Kill the Writer mid-processing, restart it, report what happened."""

    async def run() -> Dict[str, Any]:
        group = f"g_death_{commit_mode}"
        part = ordering.key_partition("victim")
        common = dict(group_id=group, commit_mode=commit_mode, offset_reset="latest")

        def new_writer() -> AgentRunner:
            return AgentRunner(
                options("writer", config.TASKS_TOPIC, config.DRAFTS_TOPIC, **common),
                make_writer(Brain("stub")),
            )

        first = await start(new_writer())
        await send(config.TASKS_TOPIC, plan_message("warmup", work_ms=0), "victim")
        await wait_until(
            lambda: committed(broker, group, config.TASKS_TOPIC, part) == 1
        )
        await send(config.TASKS_TOPIC, plan_message("slow", work_ms=3000), "victim")
        await wait_until(
            lambda: (
                first.runner.log is not None
                and committed(broker, group, config.TASKS_TOPIC, part) in (1, 2)
            )
        )
        await asyncio.sleep(0.2)  # the Writer is now inside the 3 second job
        offset_when_killed = committed(broker, group, config.TASKS_TOPIC, part)
        await first.kill()
        draft_before_restart = [
            m["correlation_id"] for m in messages_on(broker, config.DRAFTS_TOPIC)
        ]
        second = await start(new_writer())
        await asyncio.sleep(0.4)
        # finish quickly after restart: the job is long, so wait for it
        await asyncio.sleep(3.2)
        await second.kill()
        return {
            "offset_when_killed": offset_when_killed,
            "drafts_before_restart": draft_before_restart,
            "drafts_after_restart": [
                m["correlation_id"] for m in messages_on(broker, config.DRAFTS_TOPIC)
            ],
            "final_offset": committed(broker, group, config.TASKS_TOPIC, part),
        }

    return asyncio.run(run())


def test_consumer_death_commit_after_redelivers_the_message(broker: Any) -> None:
    """Commit-after-success: the killed message is redelivered and finished."""
    result = _death_scenario(broker, "after")
    assert result["offset_when_killed"] == 1  # the slow message was NOT committed
    assert result["drafts_before_restart"] == ["warmup"]
    assert result["drafts_after_restart"] == ["warmup", "slow"]
    assert result["final_offset"] == 2


def test_consumer_death_commit_on_receive_loses_the_message(broker: Any) -> None:
    """Commit-on-receive (the bug): the killed message is gone for good."""
    result = _death_scenario(broker, "on_receive")
    assert result["offset_when_killed"] == 2  # committed before the work was done
    assert result["drafts_after_restart"] == ["warmup"]  # "slow" never produced
    assert result["final_offset"] == 2


# ----------------------------------------------------- Part 3: poison message
POISON = {
    "correlation_id": "poison-1",
    "stage": "plan",
    "question": "q",
    "plan": 12345,
    "test_run": "t",
}


def test_poison_message_is_retried_then_dead_lettered_and_later_messages_flow(
    broker: Any,
) -> None:
    """3 attempts, then <PREFIX>_dead_letter, then the next message is processed."""

    async def run() -> None:
        group = "g_poison_fix"
        part = ordering.key_partition("k")
        writer = await start(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    offset_reset="latest",
                    max_attempts=3,
                    dead_letter=True,
                ),
                make_writer(Brain("stub")),
            )
        )
        await send(config.TASKS_TOPIC, POISON, "k")
        await send(config.TASKS_TOPIC, plan_message("good-after-poison"), "k")
        await wait_until(
            lambda: committed(broker, group, config.TASKS_TOPIC, part) == 2
        )
        await writer.kill()
        dead = messages_on(broker, config.DEAD_LETTER_TOPIC)
        assert len(dead) == 1
        assert dead[0]["correlation_id"] == "poison-1"
        assert dead[0]["attempts"] == 3
        assert dead[0]["failed_stage"] == "writer"
        assert "plan must be" in dead[0]["error"]
        assert json.loads(dead[0]["original"])["plan"] == 12345
        assert [
            m["correlation_id"] for m in messages_on(broker, config.DRAFTS_TOPIC)
        ] == ["good-after-poison"]

    asyncio.run(run())


def test_poison_message_without_the_fix_blocks_everything_behind_it(
    broker: Any,
) -> None:
    """Unbounded retry and no DLQ: the poison message keeps failing, nothing moves."""

    async def run() -> None:
        group = "g_poison_before"
        part = ordering.key_partition("k")
        writer = await start(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    offset_reset="latest",
                    max_attempts=0,
                    dead_letter=False,
                    backoff=0.01,
                ),
                make_writer(Brain("stub")),
            )
        )
        await send(config.TASKS_TOPIC, plan_message("warm"), "k")
        await wait_until(
            lambda: committed(broker, group, config.TASKS_TOPIC, part) == 1
        )
        await send(config.TASKS_TOPIC, POISON, "k")
        await send(config.TASKS_TOPIC, plan_message("stuck-behind"), "k")
        await asyncio.sleep(1.0)
        assert committed(broker, group, config.TASKS_TOPIC, part) == 1
        assert [
            m["correlation_id"] for m in messages_on(broker, config.DRAFTS_TOPIC)
        ] == ["warm"]
        assert messages_on(broker, config.DEAD_LETTER_TOPIC) == []
        await writer.kill()

    asyncio.run(run())


def test_bounded_retries_without_a_dead_letter_topic_stop_with_an_error(
    broker: Any,
) -> None:
    """max_attempts reached and dead_letter off: RetriesExhausted, offset not committed."""

    async def run() -> None:
        group = "g_poison_crash"
        part = ordering.key_partition("k")
        writer = Running(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    offset_reset="latest",
                    max_attempts=2,
                    dead_letter=False,
                ),
                make_writer(Brain("stub")),
            )
        )
        await writer.ready()
        await send(config.TASKS_TOPIC, POISON, "k")
        await wait_until(lambda: writer.task.done())
        assert isinstance(writer.error, RetriesExhausted)
        assert committed(broker, group, config.TASKS_TOPIC, part) is None

    asyncio.run(run())


def test_unreadable_message_is_dead_lettered_too(broker: Any) -> None:
    """A value that is not JSON is retried and moved to the dead-letter topic."""

    async def run() -> None:
        group = "g_garbage"
        part = ordering.key_partition("k")
        writer = await start(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    offset_reset="latest",
                ),
                make_writer(Brain("stub")),
            )
        )
        producer = kafka_io.make_producer()
        await producer.start()
        await producer.send_and_wait(config.TASKS_TOPIC, b"{{{ not json", key=b"k")
        await producer.stop()
        await wait_until(
            lambda: committed(broker, group, config.TASKS_TOPIC, part) == 1
        )
        await writer.kill()
        dead = messages_on(broker, config.DEAD_LETTER_TOPIC)
        assert len(dead) == 1 and dead[0]["correlation_id"] is None
        assert dead[0]["original"] == "{{{ not json"

    asyncio.run(run())


def test_transient_failure_succeeds_on_a_retry(broker: Any) -> None:
    """A handler that fails once and then works needs no dead letter."""
    calls = {"n": 0}

    async def flaky(payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model hiccup")
        return {"correlation_id": payload["correlation_id"], "ok": True}

    async def run() -> None:
        group = "g_flaky"
        part = ordering.key_partition("k")
        agent = await start(
            AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    offset_reset="latest",
                ),
                flaky,
            )
        )
        await send(config.TASKS_TOPIC, plan_message("f-1"), "k")
        await wait_until(
            lambda: committed(broker, group, config.TASKS_TOPIC, part) == 1
        )
        await agent.kill()
        assert calls["n"] == 2
        assert messages_on(broker, config.DEAD_LETTER_TOPIC) == []
        assert len(messages_on(broker, config.DRAFTS_TOPIC)) == 1

    asyncio.run(run())


# ------------------------------------------------------------ Part 3: ordering
def test_ordering_messages_are_reproducible_from_verify_seed() -> None:
    """The same VERIFY_SEED gives the same 20 messages every time."""
    a = ordering.generate_messages("t1")
    b = ordering.generate_messages("t2")
    assert len(a) == 20
    strip = lambda ms: [(m["entity"], m["seq"], m["work_ms"]) for m in ms]  # noqa: E731
    assert strip(a) == strip(b)
    assert strip(a) != strip(ordering.generate_messages("t3", seed=1))
    for entity in ordering.ENTITIES:
        seqs = [m["seq"] for m in a if m["entity"] == entity]
        assert seqs == [1, 2, 3, 4]
    assert {ordering.key_partition(e) for e in ordering.ENTITIES} == {0, 1}


def _ordering_run(broker: Any, keyed: bool, tmp_path: Any, tag: str) -> Dict[str, Any]:
    """Send the 20 messages to two Writers in one group and analyse the order."""

    async def run() -> Dict[str, Any]:
        record = tmp_path / f"{tag}.jsonl"
        group = f"g_order_{tag}"

        def writer(instance: str) -> AgentRunner:
            from pathlib import Path

            return AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    config.DRAFTS_TOPIC,
                    group_id=group,
                    instance=instance,
                    offset_reset="latest",
                ),
                make_writer(Brain("stub"), Path(record)),
            )

        a = await start(writer("A"))
        b = await start(writer("B"))
        await wait_until(
            lambda: sorted(a.runner.assigned + b.runner.assigned) == [0, 1]
        )
        already = len(messages_on(broker, config.DRAFTS_TOPIC))  # earlier runs
        for message in ordering.generate_messages(tag, work_scale=0.25):
            await send(
                config.TASKS_TOPIC, message, message["entity"] if keyed else None
            )
        await wait_until(
            lambda: len(messages_on(broker, config.DRAFTS_TOPIC)) >= already + 20,
            timeout=20,
        )
        await a.kill()
        await b.kill()
        rows = [json.loads(line) for line in record.read_text().splitlines()]
        return ordering.analyze(rows)

    return asyncio.run(run())


def test_ordering_without_a_key_breaks_order_and_a_key_fixes_it(
    broker: Any, tmp_path: Any
) -> None:
    """No key: related messages spread over 2 partitions and run out of order."""
    unkeyed = _ordering_run(broker, False, tmp_path, "nokey")
    assert unkeyed["messages_processed"] == 20
    assert unkeyed["entities_in_more_than_one_partition"] >= 1
    assert unkeyed["total_inversions"] >= 1  # the problem shows up

    keyed = _ordering_run(broker, True, tmp_path, "keyed")
    assert keyed["messages_processed"] == 20
    assert keyed["entities_in_more_than_one_partition"] == 0
    assert keyed["total_inversions"] == 0
    assert keyed["all_related_messages_in_order"] is True
    for details in keyed["entities"].values():
        assert details["processed_order"] == [1, 2, 3, 4]
        assert len(details["partitions"]) == 1
        assert len(details["instances"]) == 1


def test_two_writers_share_the_partitions_of_one_group(broker: Any) -> None:
    """Each Writer in the group gets one of the two s4833_tasks partitions."""

    async def run() -> None:
        def writer(instance: str) -> AgentRunner:
            return AgentRunner(
                options(
                    "writer",
                    config.TASKS_TOPIC,
                    None,
                    group_id="g_share",
                    instance=instance,
                    offset_reset="latest",
                ),
                make_writer(Brain("stub")),
            )

        a = await start(writer("A"))
        b = await start(writer("B"))
        await wait_until(
            lambda: sorted(a.runner.assigned + b.runner.assigned) == [0, 1]
        )
        assert len(a.runner.assigned) == 1 and len(b.runner.assigned) == 1
        await a.kill()
        await wait_until(lambda: b.runner.assigned == [0, 1])  # the survivor takes over
        await b.kill()

    asyncio.run(run())


def test_analyze_detects_an_inversion() -> None:
    """analyze() reports an entity whose messages finished out of order."""
    rows = [
        {"entity": "E", "seq": 2, "finished": 1.0, "partition": 0, "instance": "A"},
        {"entity": "E", "seq": 1, "finished": 2.0, "partition": 1, "instance": "B"},
    ]
    result = ordering.analyze(rows)
    assert result["total_inversions"] == 1
    assert result["entities"]["E"]["in_order"] is False
    assert result["entities"]["E"]["partitions"] == [0, 1]
