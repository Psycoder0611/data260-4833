# ruff: noqa: E501
"""Offline tests for HW9 (no Redis Stack, no Ollama, no MySQL needed).

    python -m pytest -q test_hw9_offline.py

Part 1 runs against fakeredis and an in-memory SQLite table. The cache logic runs
on MemorySemanticCache with a hash embedder and a scripted agent. Part 4 runs with a
scripted language model. These tests check the logic only; the reported numbers
always come from real runs.
"""

import json
from collections import Counter

import fakeredis
import pytest
import yaml
from sqlalchemy import create_engine, text

from hw9 import config, db, facts
from hw9.cache_db import ClinicalTrialCache
from hw9.embedder import HashEmbedder
from hw9.improve import reference as ref
from hw9.improve import runner
from hw9.improve.agents import AnsweringAgent, EvaluatorAgent
from hw9.improve.lessons import LessonStore
from hw9.memory_cache import MemorySemanticCache
from hw9.qa_service import QAService


@pytest.fixture()
def engine():
    """SQLite stand-in for s4833_rel.clinical_trials with the HW7 sample rows."""
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE clinical_trials (id INTEGER PRIMARY KEY, trial_code TEXT, "
                "trialTitle TEXT, sponsor TEXT, participant_capacity INTEGER, "
                "organization_id INTEGER, category TEXT, view_count INTEGER DEFAULT 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO clinical_trials (id, trial_code, trialTitle, sponsor, "
                "participant_capacity, organization_id, category) VALUES "
                "(1, 'CT-2026-101', 'Cardiac Rehabilitation Outcomes Trial', 'Stanford', 80, 2, 'Cardiology'),"
                "(2, 'CT-2026-102', 'Diabetes Prevention Lifestyle Study', 'Stanford', 200, 2, 'Endocrine')"
            )
        )
    return eng


# ------------------------------------------------------------------ Part 1
def test_counter_counts_and_syncs_every_ten(engine):
    cache = ClinicalTrialCache(fakeredis.FakeRedis(decode_responses=True), engine)
    totals = [cache.increment_clinical_trial_views(1) for _ in range(25)]
    assert totals == list(range(1, 26))
    assert db.get_view_count(engine, 1) == 20  # synced at 10 and 20, not at 25
    assert cache.views_key(1) == "s4833:views:clinical_trial:1"
    assert db.get_view_count(engine, 2) == 0


def test_every_redis_key_has_the_prefix(engine):
    client = fakeredis.FakeRedis(decode_responses=True)
    ClinicalTrialCache(client, engine).increment_clinical_trial_views(1)
    assert all(k.startswith(config.PREFIX + ":") for k in client.keys("*"))
    assert config.CACHE_KEY_PREFIX.startswith(config.PREFIX + ":")
    assert config.CACHE_INDEX.startswith(config.PREFIX + ":")


# ------------------------------------------------------------- data version
def test_record_version_changes_with_the_record(engine):
    before = db.record_version(db.get_trial_by_code(engine, "CT-2026-101"))
    db.update_capacity(engine, "CT-2026-101", 120)
    after = db.record_version(db.get_trial_by_code(engine, "CT-2026-101"))
    assert before != after


def test_facts_for(engine):
    text_, version, entity = facts.facts_for(
        engine, "What is the capacity of trial CT-2026-101?"
    )
    assert "capacity 80" in text_ and entity == "CT-2026-101" and version != "static"
    assert facts.facts_for(engine, "What is the capital of France?") == (
        "",
        "static",
        "none",
    )
    assert facts.current_version(engine, "CT-2026-101") == version


# -------------------------------------------------------------- cache logic
class ScriptedAgents:
    """Answers with the facts it is given, and counts how often it ran."""

    def __init__(self):
        self.calls = 0

    def run(self, question, facts_text=""):
        self.calls += 1
        return {
            "answer": f"ANSWER[{facts_text or question}]",
            "score": 8,
            "status": "approved",
            "agent_ms": 5.0,
        }


def make_service(engine, threshold=0.85, check_version=False):
    cache = MemorySemanticCache(HashEmbedder())
    return QAService(
        cache,
        ScriptedAgents(),
        engine,
        threshold=threshold,
        check_version=check_version,
    )


def test_miss_then_exact_duplicate_hits(engine):
    service = make_service(engine)
    q = "What is the capital of France?"
    first, second = service.answer(q), service.answer(q)
    assert first["is_cached"] is False and second["is_cached"] is True
    assert second["similarity"] >= 0.999 and second["answer"] == first["answer"]
    assert service.agents.calls == 1
    assert service.stats == {"queries": 2, "hits": 1, "misses": 1, "invalidated": 0}
    assert service.hit_rate() == 50.0


def test_unrelated_query_misses(engine):
    service = make_service(engine)
    service.answer("What is the participant capacity of trial CT-2026-101?")
    other = service.answer("How do I bake sourdough bread?")
    assert other["is_cached"] is False


def test_stale_hit_without_check_and_invalidation_with_check(engine):
    q = "What is the participant capacity of trial CT-2026-101?"
    service = make_service(engine)
    assert "capacity 80" in service.answer(q)["answer"]
    db.update_capacity(engine, "CT-2026-101", 120)
    stale = service.answer(q)
    assert stale["is_cached"] is True and "capacity 80" in stale["answer"]  # stale!
    service.check_version = True
    fresh = service.answer(q)
    assert fresh["is_cached"] is False and fresh["invalidated"] is True
    assert "capacity 120" in fresh["answer"]
    assert service.answer(q)["is_cached"] is True  # new entry is served again


def test_cases_file_is_complete():
    spec = yaml.safe_load(config.CASES_PATH.read_text(encoding="utf-8"))
    assert len(spec["seed_queries"]) == 10 and len(spec["cases"]) == 40
    assert Counter(c["type"] for c in spec["cases"]) == {
        "exact_duplicate": 10, "paraphrase": 10, "similar_different": 10, "unrelated": 10,
    }  # fmt: skip
    assert len({c["id"] for c in spec["cases"]}) == 40
    seed_ids = {s["id"] for s in spec["seed_queries"]}
    for case in spec["cases"]:
        assert case["expected_hit"] == (
            case["type"] in ("exact_duplicate", "paraphrase")
        )
        assert case["seed"] is None or case["seed"] in seed_ids
    seeds = {s["id"]: s["query"] for s in spec["seed_queries"]}
    for case in spec["cases"]:
        if case["type"] == "exact_duplicate":
            assert case["query"] == seeds[case["seed"]]


# ------------------------------------------------------------------- Part 4
REFERENCE = ref.load_reference()


def questions(name):
    return json.loads(
        (config.DATA_DIR / f"{name}_data.json").read_text(encoding="utf-8")
    )


def test_datasets_contain_only_questions():
    for name, size in (("training", 12), ("validation", 12), ("test", 16)):
        rows = questions(name)
        assert len(rows) == size
        assert all(set(r) == {"id", "question"} for r in rows)
    texts = [
        r["question"] for n in ("training", "validation", "test") for r in questions(n)
    ]
    assert len(texts) == len(set(texts))  # no question is reused across the sets


def test_every_in_domain_question_matches_exactly_one_entry():
    for name in ("training", "validation", "test"):
        for row in questions(name):
            q = row["question"].lower()
            best = 0
            for entry in REFERENCE["entries"]:
                for group in entry["triggers"]:
                    if all(w in q for w in group):
                        best = max(best, len(group))
            winners = {
                e["id"]
                for e in REFERENCE["entries"]
                for g in e["triggers"]
                if all(w in q for w in g) and len(g) == best
            }
            assert len(winners) <= 1, (row, winners)


INTENDED = {  # test-only check that the matcher finds the entry I meant
    "How many characters can a trial description contain at most?": "ref_description_len",
    "How long may a trial title be?": "ref_title_len",
    "Which topic receives messages that keep failing?": "ref_dead_letter_topic",
    "Where do poison messages end up after the retries are used up?": "ref_dead_letter_topic",
    "How many participants can enroll in trial CT-2026-102?": "ref_ct102_capacity",
    "What is the title of trial CT-2026-101?": "ref_ct101_title",
    "What phase is trial CT-2026-103 in?": "ref_no_phase",
    "Who is the principal investigator of trial CT-2026-105?": "ref_no_investigator",
    "What character must a valid submitter email contain?": "ref_email_format",
    "What is the minimum participant capacity of a trial?": "ref_min_capacity",
    "When does enrollment start for trial CT-2026-104?": "ref_no_dates",
    "When does an agent commit a Kafka offset?": "ref_offset_commit",
    "Which fields must be provided to create a trial listing?": "ref_required_fields",
    "What review score does the Reviewer need to approve a draft?": "ref_approval_score",
    "How many attempts does an agent make before a message is dead-lettered?": "ref_max_attempts",
    "How long can a trial code be?": "ref_code_len",
    "What is the name of trial CT-2026-105?": "ref_ct105_title",
    "What is the capacity of trial CT-2026-103?": "ref_ct103_capacity",
}


def test_matcher_finds_the_intended_entry():
    for question, entry_id in INTENDED.items():
        assert ref.match_entry(REFERENCE, question)["id"] == entry_id, question
    assert ref.match_entry(REFERENCE, "What is the capital of Japan?") is None


def test_check_answer_rules():
    q = "How many characters can a trial description contain at most?"
    assert ref.check_answer(REFERENCE, q, "At most 2,000 characters.").passed
    assert not ref.check_answer(REFERENCE, q, "At most 20000 characters.").passed
    assert not ref.check_answer(REFERENCE, q, "It can be fairly long.").passed
    q2 = "What phase is trial CT-2026-101 in?"
    assert ref.check_answer(
        REFERENCE, q2, "The phase is not available in the listing."
    ).passed
    assert not ref.check_answer(REFERENCE, q2, "It is a Phase III trial.").passed
    q3 = "What is the capital of Japan?"
    assert ref.check_answer(REFERENCE, q3, "Tokyo.").passed
    assert not ref.check_answer(
        REFERENCE, q3, "Tokyo. The description limit is 2000 characters."
    ).passed
    q4 = "Which fields are required to create a trial listing?"
    verdict = ref.check_answer(REFERENCE, q4, "Title and sponsor.")
    assert verdict.result == "REVISE" and "Reference" in verdict.feedback


def scripted(replies):
    """A fake language model that returns the given replies in order (last repeats)."""
    state = {"i": 0, "prompts": []}

    def llm(messages):
        state["prompts"].append(messages)
        reply = replies[min(state["i"], len(replies) - 1)]
        state["i"] += 1
        return reply

    llm.state = state
    return llm


def test_repair_revises_once_and_stops_after_two_attempts():
    q = "How many characters can a trial description contain at most?"
    good = scripted(["Not sure.", "At most 2000 characters."])
    result = runner.solve(q, AnsweringAgent(llm=good), EvaluatorAgent(), repair=True)
    assert (
        result["attempt_count"] == 2
        and result["correct"]
        and result["first_result"] == "REVISE"
    )
    assert "Evaluator feedback" in good.state["prompts"][1][1]["content"]
    never = scripted(["Not sure.", "Still not sure.", "third"])
    result = runner.solve(q, AnsweringAgent(llm=never), EvaluatorAgent(), repair=True)
    assert result["attempt_count"] == 2 and not result["correct"]  # stops at two
    baseline = runner.solve(
        q, AnsweringAgent(llm=scripted(["Not sure."])), EvaluatorAgent(), repair=False
    )
    assert baseline["attempt_count"] == 1


def test_controlled_first_answer():
    q = "How many characters can a trial description contain at most?"
    llm = scripted(["At most 2000 characters."])
    result = runner.solve(
        q,
        AnsweringAgent(llm=llm),
        EvaluatorAgent(),
        True,
        controlled_first="It can be long.",
    )
    assert (
        result["attempts"][0]["answer"] == "It can be long."
        and result["attempt_count"] == 2
    )
    assert len(llm.state["prompts"]) == 1  # the model was only asked for the revision


def test_lessons_are_proposed_stored_loaded_and_counted(tmp_path):
    evaluator = EvaluatorAgent()
    failures = [
        {"question": "q1", "topic": "field_limits", "entry_id": "ref_description_len"},
        {"question": "q2", "topic": "field_limits", "entry_id": "ref_title_len"},
        {"question": "q3", "topic": "message_handling", "entry_id": "ref_max_attempts"},
    ]
    proposals = evaluator.propose_lessons(failures)
    assert [p["topic"] for p in proposals] == [
        "field_limits"
    ]  # only the repeated pattern
    assert "2000" in proposals[0]["correction"] and "255" in proposals[0]["correction"]
    store = LessonStore(tmp_path / "lessons.json")
    lesson = store.add(
        proposals[0]["failure_pattern"], proposals[0]["correction"], "field_limits"
    )
    assert set(lesson) >= {
        "lesson_id",
        "failure_pattern",
        "correction",
        "created_at",
        "use_count",
    }
    assert lesson["lesson_id"] == "lesson_001" and lesson["use_count"] == 0
    llm = scripted(["At most 2000 characters."])
    agent = AnsweringAgent(llm=llm, lessons=store)
    result = runner.solve(
        "What is the maximum number of characters allowed in a trial description?",
        agent,
        evaluator,
        False,
    )
    assert result["attempts"][0]["lessons_loaded"] == ["lesson_001"]
    assert "2000" in llm.state["prompts"][0][0]["content"]
    assert LessonStore(tmp_path / "lessons.json").lessons[0]["use_count"] == 1
    unrelated = runner.solve(
        "What is the capital of Japan?",
        AnsweringAgent(llm=scripted(["Tokyo."]), lessons=store),
        evaluator,
        False,
    )
    assert unrelated["attempts"][0]["lessons_loaded"] == []


def test_lesson_filters(tmp_path):
    store = LessonStore(tmp_path / "l.json")
    a = store.add(
        "pattern about trial title length", "title limit 255 characters", "field_limits"
    )
    b = store.add(
        "pattern about trial title length", "title limit 255 characters", "field_limits"
    )
    b["status"] = "kept"
    q = "How many characters can a trial title have?"
    assert len(store.relevant(q)) == 2
    assert [x["lesson_id"] for x in store.relevant(q, statuses=["kept"])] == [
        b["lesson_id"]
    ]
    assert store.relevant(q, ids=[]) == [] and a["status"] == "candidate"


def test_summary_numbers():
    rows = [
        {"correct": True, "attempt_count": 1, "latency_ms": 10.0},
        {"correct": False, "attempt_count": 2, "latency_ms": 30.0},
    ]
    assert runner.summarize(rows) == {
        "correct": 1,
        "incorrect": 1,
        "avg_attempts": 1.5,
        "avg_latency_ms": 20.0,
    }


def test_lesson_relevance_uses_specific_words(tmp_path):
    store = LessonStore(tmp_path / "l.json")
    reference = ref.load_reference()
    info = reference["topics"]["unavailable_data"]
    store.add(info["failure_pattern"], info["instruction"], "unavailable_data")
    info = reference["topics"]["field_limits"]
    store.add(
        info["failure_pattern"],
        info["instruction"] + " A description is at most 2000 characters.",
        "field_limits",
    )
    pick = lambda q: [x["topic"] for x in store.relevant(q)]  # noqa: E731
    assert pick("What phase is trial CT-2026-101 in?") == ["unavailable_data"]
    assert pick("Who is the principal investigator of trial CT-2026-104?") == [
        "unavailable_data"
    ]
    assert pick(
        "What is the maximum number of characters allowed in a trial description?"
    ) == ["field_limits"]
    assert pick("What is the capital of Japan?") == []
    assert pick("Who painted Starry Night?") == []


def test_threshold_sweep_arithmetic():
    import run_hw09_part3 as part3

    spec = part3.load_cases()
    answers = {
        q: {
            "answer": f"A:{q}",
            "agent_ms": 100.0,
            "data_version": "static",
            "entity": "none",
        }
        for q in part3.distinct_queries(spec)
    }
    cache = MemorySemanticCache(HashEmbedder())
    for seed in spec["seed_queries"]:
        cache.store(seed["query"], answers[seed["query"]]["answer"])
    everything = part3.run_threshold(cache, spec, answers, -1.0)
    assert (
        everything["hit_rate_pct"] == 100.0
        and everything["false_hit_rate_pct"] == 100.0
    )
    assert everything["total_cost"] == round(20 * config.COST_FALSE_HIT, 2)
    nothing = part3.run_threshold(cache, spec, answers, 1.01)
    assert nothing["hit_rate_pct"] == 0.0 and nothing["false_hit_rate_pct"] == 0.0
    assert nothing["missed_hits"] == 20 and nothing["total_cost"] == round(
        40 * config.COST_MISS, 2
    )
    assert nothing["mean_latency_ms"] >= 100.0
    exact = [
        r
        for r in part3.run_threshold(cache, spec, answers, 0.99)["rows"]
        if r["type"] == "exact_duplicate"
    ]
    assert all(r["hit"] for r in exact)
