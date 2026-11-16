# ruff: noqa: E501
"""Offline tests for HW10 (no Kafka, Redis, Ollama or MySQL needed).

    python -m pytest -q test_hw10_offline.py

The pipeline runs on the in-memory broker from hw8/fake_kafka.py with the stub Brain and
a hash-embedding cache; the judge uses a scripted chat function. These tests check the
logic (span schema, trace_id propagation, hit/miss/failed traces, join, bounded
evaluation, statistics, dashboard pages). Reported numbers always come from real runs.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from hw8 import fake_kafka
from hw8.pipeline import Brain
from hw9.embedder import HashEmbedder
from hw9.memory_cache import MemorySemanticCache

from hw10 import collector, config, evaluator, stats, tracing
from hw10.ingress import TracedIngress
from hw10.judge import OllamaJudge, band_for, score_text
from hw10.kafka_trace import FAULT_BAD_PLAN, build_runner


@pytest.fixture()
def env(monkeypatch: Any, tmp_path: Path) -> Dict[str, Any]:
    """Fake broker + temp output folders."""
    broker = fake_kafka.FakeBroker(seed=5)
    fake_kafka.install(monkeypatch, broker)
    monkeypatch.setattr(config, "SPANS_PATH", tmp_path / "spans.jsonl")
    monkeypatch.setattr(config, "JOINED_DIR", tmp_path / "joined")
    return {"broker": broker, "dir": tmp_path}


def good_chat(prompt: str, schema: Any) -> str:
    """Scripted judge: always answers score 8 (band 4)."""
    return json.dumps({"score": 8, "reason": "scripted"})


async def wait_ready(runners: List[Any]) -> List[asyncio.Task]:
    """Start the agents and wait until all report their partitions."""
    tasks = [asyncio.create_task(r.run()) for r in runners]
    for _ in range(200):
        if all(r.assigned for r in runners):
            break
        await asyncio.sleep(0.02)
    return tasks


def run_pipeline(coro_factory):
    """Run `coro_factory(ingress)` with three traced agents and an ingress."""

    async def main():
        brain = Brain("stub")
        runners = [build_runner(r, brain, store_path=":memory:", backoff=0.0) for r in ("planner", "writer", "reviewer")]
        tasks = await wait_ready(runners)
        cache = MemorySemanticCache(HashEmbedder())
        ingress = TracedIngress(cache, engine=None, timeout=10, check_version=False)
        await ingress.start()
        try:
            return await coro_factory(ingress)
        finally:
            await ingress.stop()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return asyncio.run(main())


def stages(trace_id: str) -> List[str]:
    """Stage names of one trace in time order."""
    return [s["stage"] for s in tracing.group_by_trace(tracing.read_spans())[trace_id]]


def test_span_schema_and_trace_id_is_the_correlation_id(env: Any) -> None:
    async def go(ingress):
        return await ingress.ask("What is the capacity of CT-2026-101?")

    result = run_pipeline(go)
    tid = result["trace_id"]
    assert result["status"] == "ok" and result["path"] == "miss"
    spans = tracing.group_by_trace(tracing.read_spans())[tid]
    for span in spans:
        assert {"trace_id", "stage", "start", "end", "status", "error"} <= span.keys()
        assert span["trace_id"] == tid
        assert tracing.parse_iso(span["end"]) >= tracing.parse_iso(span["start"])
    got = [s["stage"] for s in spans]
    for needed in ("cache_lookup", "queue_inbox", "planner", "queue_tasks", "writer",
                   "queue_drafts", "reviewer", "queue_final", "request"):
        assert needed in got, got
    # every Kafka message of the request carries the same id
    bundle = result["bundle"]
    for role in ("plan", "draft", "final"):
        assert bundle[role]["value"]["correlation_id"] == tid
    assert (env["dir"] / "joined" / f"{tid}.json").exists()


def test_cache_hit_trace_has_no_pipeline_stages(env: Any) -> None:
    async def go(ingress):
        first = await ingress.ask("Which sponsor runs the diabetes prevention study?")
        second = await ingress.ask("Which sponsor runs the diabetes prevention study?")
        return first, second

    first, second = run_pipeline(go)
    assert first["path"] == "miss" and second["path"] == "hit"
    assert second["answer"] == first["answer"]
    assert stages(second["trace_id"]) == ["cache_lookup", "request"]
    spans = tracing.group_by_trace(tracing.read_spans())[second["trace_id"]]
    assert spans[0]["attrs"]["cache_hit"] is True
    assert tracing.trace_path(spans) == "hit"


def test_failed_trace_names_the_failing_stage_and_error(env: Any) -> None:
    async def go(ingress):
        return await ingress.ask("Explain the enrollment steps.", fault=FAULT_BAD_PLAN)

    result = run_pipeline(go)
    assert result["status"] == "error"
    spans = tracing.group_by_trace(tracing.read_spans())[result["trace_id"]]
    failing = tracing.failing_stage(spans)
    assert failing["stage"] == "writer"
    assert "plan must be a non-empty list" in failing["error"]
    writer_errors = [s for s in spans if s["stage"] == "writer" and s["status"] == "error"]
    assert len(writer_errors) == 3  # HW8 retry rule: 3 attempts
    assert "dead_letter" in [s["stage"] for s in spans]
    assert tracing.trace_status(spans) == "error"


def test_join_keeps_messages_and_reports_malformed(env: Any) -> None:
    rows = [
        {"topic": config.TASKS_TOPIC, "partition": 0, "offset": 0, "value": {"correlation_id": "a", "plan": ["x"], "question": "q"}},
        {"topic": config.DRAFTS_TOPIC, "partition": 0, "offset": 0, "value": {"correlation_id": "a", "draft": "d", "question": "q"}},
        {"topic": config.FINAL_TOPIC, "partition": 0, "offset": 0, "value": {"correlation_id": "a", "answer": "d", "status": "approved", "score": 8}},
        {"topic": config.DRAFTS_TOPIC, "partition": 0, "offset": 1, "value": {"_malformed": "not json"}},
        {"topic": config.TASKS_TOPIC, "partition": 0, "offset": 1, "value": {"correlation_id": "b", "plan": []}},
    ]
    joined = collector.join_by_correlation(rows)
    assert joined["a"]["issues"] == []
    assert joined["a"]["final"]["value"]["answer"] == "d"
    assert "plan is empty or not a list" in joined["b"]["issues"]
    assert "missing draft message" in joined["b"]["issues"]
    assert joined["_unjoined"]["issues"]


def bundle(plan=("a", "b", "c"), draft="A clear draft.", answer=None, final_status="approved") -> Dict[str, Any]:
    """A joined bundle shaped like collector.bundle_for()."""
    row = lambda topic, value: {"topic": topic, "partition": 0, "offset": 0, "value": value}  # noqa: E731
    return {
        "trace_id": "t1",
        "plan": row("p", {"correlation_id": "t1", "question": "q?", "plan": list(plan)}),
        "draft": row("d", {"correlation_id": "t1", "question": "q?", "draft": draft}),
        "final": row("f", {"correlation_id": "t1", "answer": answer or draft, "status": final_status, "score": 8}),
        "issues": [],
    }


def test_evaluator_record_has_all_four_criteria(env: Any) -> None:
    judge = OllamaJudge(chat_fn=good_chat)
    record = evaluator.evaluate_bundle(bundle(), judge)
    assert record["plan_quality"]["score"] == 4 and record["plan_quality"]["reason"]
    assert record["writer_helpfulness"]["trace_id"] == "t1"
    assert record["final_helpfulness"]["final_answer"] == "A clear draft."
    imp = record["improvement"]
    assert (imp["draft_score"], imp["final_score"], imp["difference"]) == (4, 4, 0)
    assert "word for word" in imp["interpretation"]
    spans = tracing.read_spans()
    assert [s["stage"] for s in spans] == ["evaluation"] and spans[0]["trace_id"] == "t1"


def test_evaluator_is_bounded_when_the_judge_is_down_or_input_is_bad(env: Any) -> None:
    def down(prompt: str, schema: Any) -> str:
        from hw10.judge import JudgeError

        raise JudgeError("local judge call failed: connection refused")

    judge = OllamaJudge(chat_fn=down)
    record = evaluator.evaluate_bundle(bundle(), judge)
    assert record["status"] == "error"
    assert record["writer_helpfulness"]["status"] == "judge_error"
    assert record["improvement"]["difference"] is None
    # malformed messages: the plan is empty, the draft is missing -> invalid_input, no crash
    broken = bundle(plan=())
    broken["draft"] = None
    good = OllamaJudge(chat_fn=good_chat)
    record = evaluator.evaluate_bundle(broken, good)
    assert record["plan_quality"]["status"] == "invalid_input"
    assert record["writer_helpfulness"]["status"] == "invalid_input"
    assert record["final_helpfulness"]["status"] == "ok"


def test_a_hanging_judge_times_out(env: Any) -> None:
    def slow(prompt: str, schema: Any) -> str:
        time.sleep(3)
        return good_chat(prompt, schema)

    started = time.time()
    result = score_text("helpfulness", "q", "a", OllamaJudge(chat_fn=slow), timeout=0.3)
    assert result["status"] == "timeout" and result["score"] is None
    assert time.time() - started < 2


def test_band_mapping() -> None:
    assert [band_for(x) for x in (0, 2, 3, 4, 5, 6, 7, 8, 9, 10)] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_percentiles_shares_and_validation_stats() -> None:
    def span(stage, ms):
        return {"trace_id": "x", "stage": stage, "duration_ms": ms, "status": "ok", "start": "", "end": ""}

    traces = {
        f"t{i}": [span("cache_lookup", 100), span("planner", 1000), span("queue_inbox", 50),
                  span("writer", 3000), span("reviewer", 1000), span("evaluation", 850)]
        for i in range(5)
    }
    table = stats.miss_latency_table(traces)
    rows = {r["stage"]: r for r in table["rows"]}
    assert rows["Writer"]["p50_ms"] == 3000 and rows["Writer"]["share_pct"] == pytest.approx(50.0, abs=0.1)
    assert rows["End-to-end (all stages above)"]["p95_ms"] == 6000
    out = stats.validation_stats([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert out["spearman"] == 1.0 and out["mad"] == 0
    out = stats.validation_stats([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert out["spearman"] == -1.0 and out["mad"] == pytest.approx(2.4)
    rep = stats.repeatability([{"a": 3, "b": 4}, {"a": 3, "b": 5}, {"a": 4, "b": 5}])
    assert rep["cases_changed"] == 2 and rep["mean_abs_change"] == 1.0 and rep["max_abs_change"] == 1.0
    assert stats.validation_stats([3, 3, 3], [1, 2, 3])["spearman"] is None


def test_dashboard_pages_render_from_sample_data(env: Any, monkeypatch: Any) -> None:
    from streamlit.testing.v1 import AppTest

    tid = "sample-trace-1"
    now = time.time()
    for i, (stage, d) in enumerate([("cache_lookup", 0.1), ("planner", 1.0), ("writer", 2.0), ("reviewer", 1.0)]):
        tracing.record(tid, stage, now + i, now + i + d, attrs={"cache_hit": False} if stage == "cache_lookup" else {})
    tracing.record(tid, "request", now, now + 5, attrs={"path": "miss"})
    monkeypatch.setenv("HW10_SPAN_PATH", str(config.SPANS_PATH))
    monkeypatch.setenv("HW10_REPORT_DIR", str(env["dir"]))
    app = AppTest.from_file(str(Path(__file__).parent / "hw10_dashboard.py"), default_timeout=30)
    app.run()
    assert not app.exception, [e.value for e in app.exception]


def test_part3_scripts_score_validate_and_check_repeatability(env: Any, monkeypatch: Any) -> None:
    import csv

    import run_hw10_part3 as p3

    data = env["dir"] / "data"
    data.mkdir()
    cases = [{"case_id": f"C{i:02d}", "question": f"q{i}", "facts": "", "judge_input": f"q{i}", "plan": ["a"], "draft": f"draft {i}"} for i in range(1, 21)]
    (data / "cases.json").write_text(json.dumps({"cases": cases}))
    with open(data / "labels.csv", "w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["case_id", "human_score", "labeled_at"])
        for i in range(1, 21):
            w.writerow([f"C{i:02d}", (i % 5) + 1, "x"])
    monkeypatch.setattr(config, "CASES_PATH", data / "cases.json")
    monkeypatch.setattr(config, "LABELS_PATH", data / "labels.csv")
    monkeypatch.setattr(config, "RAW_DIR", env["dir"] / "raw")
    monkeypatch.setattr(p3, "committed_state", lambda: {"commit": "abc", "committed_at": "now"})
    monkeypatch.setattr(p3, "check_ollama", lambda models: [])
    calls = {"n": 0}

    def chat(prompt: str, schema: Any) -> str:
        calls["n"] += 1
        # the judge copies the human label from the text, except it is off by one on every 7th call
        return json.dumps({"score": 2 * (((calls["n"] - 1) % 20) % 5 + 1) - 1 if calls["n"] % 7 else 9, "reason": "r"})

    monkeypatch.setattr(p3, "make_judge", lambda: OllamaJudge(chat_fn=chat))
    for n in (1, 2, 3):
        p3.judge_run(n)
    p3.compute_stats()
    out = json.loads((config.RAW_DIR / "part3_validation.json").read_text())
    assert out["validation"]["n"] == 20 and out["repeatability"]["runs"] == 3
    assert (config.RAW_DIR / "part3_per_case.csv").exists()
    assert out["cases"][0]["judge_run3"] is not None
