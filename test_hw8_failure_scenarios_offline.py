# ruff: noqa: E501
"""Offline test of the Part 3 scenario code (hw8/failure_tests.py).

The same scenario functions that produce the reported results run here against
the in-memory broker with the Writer inside this process, scaled down so the
test is quick. Run:  pytest -q test_hw8_failure_scenarios_offline.py
"""

import asyncio
from pathlib import Path
from typing import Any

from hw8 import failure_tests, fake_kafka
from hw8.logs import read_jsonl


def run(coro: Any) -> Any:
    """Run a coroutine to completion."""
    return asyncio.run(coro)


def test_duplicate_scenario(monkeypatch: Any, tmp_path: Path) -> None:
    """Without idempotency the replay makes 2 drafts; with it, 1 and a DUPLICATE line."""
    fake_kafka.install(monkeypatch, fake_kafka.FakeBroker(seed=5))
    result = run(
        failure_tests.scenario_duplicate(
            failure_tests.InProcessLauncher(), "t", tmp_path
        )
    )
    assert result["before"]["drafts_produced"] == 2
    assert result["before"]["duplicates_skipped"] == 0
    assert result["after"]["drafts_produced"] == 1
    assert result["after"]["duplicates_skipped"] == 1
    assert any("DUPLICATE" in line for line in result["after"]["writer_log"])


def test_consumer_death_scenario(monkeypatch: Any, tmp_path: Path) -> None:
    """Commit-on-receive loses the killed message; commit-after redelivers it."""
    fake_kafka.install(monkeypatch, fake_kafka.FakeBroker(seed=5))
    result = run(
        failure_tests.scenario_death(
            failure_tests.InProcessLauncher(),
            "t",
            tmp_path,
            victim_ms=700,
            redelivery_wait=1.5,
        )
    )
    before, after = result["before"], result["after"]
    assert before["victim_redelivered_after_restart"] is False
    assert before["victim_draft_produced"] is False
    assert after["victim_redelivered_after_restart"] is True
    assert after["victim_draft_produced"] is True
    # the offset was NOT past the victim when it was killed, and is after the restart
    killed = list(after["committed_offsets_when_killed"].values())
    final = list(after["final_committed_offsets"].values())
    assert (
        max(f for f in final if f is not None)
        == max(k for k in killed if k is not None) + 1
    )
    # without the fix the offset was already past the victim at kill time
    killed_before = max(
        v for v in before["committed_offsets_when_killed"].values() if v
    )
    assert killed_before == max(
        v for v in before["final_committed_offsets"].values() if v
    )


def test_poison_scenario(monkeypatch: Any, tmp_path: Path) -> None:
    """Without the fix the good message is stuck; with it, DLQ and the flow goes on."""
    fake_kafka.install(monkeypatch, fake_kafka.FakeBroker(seed=5))
    result = run(
        failure_tests.scenario_poison(
            failure_tests.InProcessLauncher(), "t", tmp_path, observe_seconds=1.5
        )
    )
    before, after = result["before"], result["after"]
    assert before["good_message_processed"] is False
    assert before["dead_letter_messages"] == []
    assert before["failed_attempts"] >= 3
    assert after["good_message_processed"] is True
    assert after["failed_attempts"] == 3
    assert len(after["dead_letter_messages"]) == 1
    assert after["dead_letter_messages"][0]["attempts"] == 3


def test_ordering_scenario(monkeypatch: Any, tmp_path: Path) -> None:
    """Unkeyed run breaks related-message order; the keyed run keeps it."""
    fake_kafka.install(monkeypatch, fake_kafka.FakeBroker(seed=3))
    result = run(
        failure_tests.scenario_ordering(
            failure_tests.InProcessLauncher(),
            "t",
            tmp_path / "state",
            tmp_path / "raw",
            work_scale=0.25,
        )
    )
    unkeyed = result["unkeyed"]["analysis"]
    keyed = result["keyed"]["analysis"]
    assert unkeyed["total_inversions"] >= 1
    assert unkeyed["entities_in_more_than_one_partition"] >= 1
    assert keyed["total_inversions"] == 0
    assert keyed["entities_in_more_than_one_partition"] == 0
    assert keyed["messages_processed"] == 20
    for mode in ("unkeyed", "keyed"):
        assert (tmp_path / "raw" / f"part3_ordering_{mode}_sent.csv").exists()
        assert (tmp_path / "raw" / f"part3_ordering_{mode}_processed.csv").exists()
        assert (
            len(read_jsonl(tmp_path / "raw" / f"part3_ordering_{mode}_processed.jsonl"))
            == 20
        )
