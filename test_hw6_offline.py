"""Offline tests for HW6 (mongomock + fake model). No Docker or Ollama needed."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import mongomock
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hw6 import file_memory, llm, memory
from hw6 import mongo as hw6_mongo
from routers import hw6_chat, hw6_trials

ROOT = Path(__file__).resolve().parent


# ------------------------------------------------------------------ fakes


def fake_embedding(text: str) -> list:
    """Bag-of-words hashing vector so similar words give similar vectors."""
    vector = [0.0] * 64
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % 64
        vector[slot] += 1.0
    return vector


def fake_chat(messages: list) -> dict:
    """Pretend model: returns JSON for extraction, bullets for summaries, text otherwise."""
    system = messages[0]["content"]
    last = messages[-1]["content"]
    prompt_tokens = sum(len(m["content"]) for m in messages) // 4
    if "Extract up to 3" in system:
        user_text = last.split('"""')[1]
        facts = [{"fact": s.strip()[:80], "importance": 0.8} for s in re.split(r"[.!?]", user_text) if "my " in s.lower() or "i'm" in s.lower()]
        content = json.dumps(facts[:3])
    elif "Merge these notes" in system:
        content = "- lifetime bullet"
    elif "Update the running summary" in system:
        content = "- summary bullet"
    else:
        content = "Noted: " + last[:40]
    return {"content": content, "input_tokens": prompt_tokens, "output_tokens": 10, "latency_ms": 1.0}


@pytest.fixture(autouse=True)
def fake_backends(monkeypatch):
    """Use an in-memory MongoDB and the fake model for every test."""
    hw6_mongo.use_client(mongomock.MongoClient(tz_aware=True))
    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "embed", fake_embedding)
    yield
    hw6_mongo.use_client(mongomock.MongoClient(tz_aware=True))


@pytest.fixture()
def client():
    """FastAPI test client with only the HW6 routers."""
    app = FastAPI()
    app.include_router(hw6_trials.router)
    app.include_router(hw6_chat.router)
    return TestClient(app)


VALID_TRIAL = {
    "trialTitle": "Glucose Monitoring Study",
    "description": "Study evaluating glucose tracking in adults.",
    "phase": "phase2",
    "scheduledDate": "2026-10-15T10:00:00",
}


# -------------------------------------------------------- Part 1: trials


def test_trial_crud_cycle(client):
    created = client.post("/api/hw6/trials", json=VALID_TRIAL)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "recruiting"  # default
    assert body["createdAt"] and body["updatedAt"]
    trial_id = body["id"]
    assert len(client.get("/api/hw6/trials").json()) == 1
    assert client.get(f"/api/hw6/trials/{trial_id}").json()["trialTitle"] == VALID_TRIAL["trialTitle"]
    updated = client.put(f"/api/hw6/trials/{trial_id}", json={"status": "active"})
    assert updated.status_code == 200 and updated.json()["status"] == "active"
    assert client.delete(f"/api/hw6/trials/{trial_id}").status_code == 204
    assert client.get(f"/api/hw6/trials/{trial_id}").status_code == 404


def test_trial_validation_errors(client):
    missing = {key: value for key, value in VALID_TRIAL.items() if key != "trialTitle"}
    assert client.post("/api/hw6/trials", json=missing).status_code == 422
    assert client.post("/api/hw6/trials", json={**VALID_TRIAL, "status": "paused"}).status_code == 422
    assert client.post("/api/hw6/trials", json={**VALID_TRIAL, "phase": "phase9"}).status_code == 422
    assert client.post("/api/hw6/trials", json={**VALID_TRIAL, "trialTitle": "x" * 101}).status_code == 422
    assert client.post("/api/hw6/trials", json={**VALID_TRIAL, "scheduledDate": "not-a-date"}).status_code == 422
    assert client.post("/api/hw6/trials", json={**VALID_TRIAL, "trialTitle": 123}).status_code == 422


def test_trial_bad_and_unknown_ids(client):
    assert client.get("/api/hw6/trials/not-an-id").status_code == 400
    assert client.get("/api/hw6/trials/64b64b64b64b64b64b64b64b").status_code == 404
    assert client.put("/api/hw6/trials/64b64b64b64b64b64b64b64b", json={"status": "active"}).status_code == 404
    assert client.put("/api/hw6/trials/64b64b64b64b64b64b64b64b", json={}).status_code == 400
    assert client.delete("/api/hw6/trials/64b64b64b64b64b64b64b64b").status_code == 404


# ----------------------------------------------------- Part 2: memory


def test_cosine_similarity():
    assert memory.cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert memory.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert memory.cosine_similarity([0, 0], [1, 1]) == 0.0


def test_chat_ten_messages_builds_all_memory_layers(client):
    messages = [
        "I'm Dana and my cat is Biscuit.", "My trip is to Iceland in March.", "What is the weather like?",
        "My budget is 4500 dollars.", "Tell me a joke.", "My co-author is Lena.", "Any packing tips?",
        "I'm vegetarian so plan food.", "How cold is it?", "My camera is a Nikon.", "Thanks!",
    ]
    last = None
    for text in messages:
        response = client.post("/api/chat", json={"user_id": "u1", "session_id": "s1", "message": text})
        assert response.status_code == 200
        last = response.json()
    assert last["memory_used"]["short_term_count"] == 12  # default window N=12
    assert last["memory_used"]["session_summary"] == "- summary bullet"
    first = client.post("/api/chat", json={"user_id": "u1", "session_id": "s1", "message": "what is my cat called Biscuit?"}).json()
    assert any("cat" in item["fact"].lower() for item in first["memory_used"]["episodic_facts"])
    usage = first["usage"]
    parts = ["system_primer_tokens", "long_term_tokens", "short_term_tokens", "episodic_tokens", "current_message_tokens"]
    assert sum(usage[name] for name in parts) == usage["prompt_tokens"]
    view = client.get("/api/memory/u1").json()
    assert len(view["messages"]) <= 16 and view["session_summary"] and view["episodes"]
    assert "embedding" not in view["episodes"][0]
    aggregate = client.get("/api/aggregate/u1").json()
    assert sum(day["messages"] for day in aggregate["daily_message_counts"]) == 24
    assert aggregate["recent_summaries"]


def test_lifetime_summary_is_created_after_three_session_summaries(client):
    for index in range(15):
        client.post("/api/chat", json={"user_id": "u2", "session_id": "s", "message": f"message {index}"})
    lifetime = memory.latest_summary("u2", "user")
    assert lifetime is not None and lifetime["session_id"] is None and lifetime["scope"] == "user"


def test_probe_mode_does_not_store_anything(client):
    client.post("/api/chat", json={"user_id": "u3", "session_id": "s", "message": "My dog is Rex."})
    before = hw6_mongo.get_collection("messages").count_documents({})
    client.post("/api/chat", json={"user_id": "u3", "session_id": "s", "message": "probe?", "persist": False})
    assert hw6_mongo.get_collection("messages").count_documents({}) == before


def test_chat_validation(client):
    assert client.post("/api/chat", json={"user_id": "u", "message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 422


def test_compression_policy_shrinks_older_messages():
    window = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"message number {i} " * 10} for i in range(20)]
    cfg = memory.MemoryConfig(policy="compress_older", keep_recent=6)
    digest, verbatim = memory.apply_policy(window, cfg)
    assert len(verbatim) == 6 and digest.count("\n") + 1 == 7  # 14 older msgs -> 7 user bullets
    assert memory.apply_policy(window, memory.MemoryConfig())[0] == ""


# ------------------------------------------------------ Part 3: probes


def test_probe_scoring_formula():
    import run_hw06_memory_experiment as experiment

    probes = yaml.safe_load((ROOT / "reports" / "hw06" / "memory_probes.yaml").read_text())["probes"]
    assert len(probes) == 5 and all(len(probe["facts"]) == 3 for probe in probes)
    assert experiment.score_answer("You are Dana, an ecologist in Monterey.", probes[0])["score"] == 5
    assert experiment.score_answer("You are Dana, an ecologist.", probes[0])["score"] == 4
    assert experiment.score_answer("Dana.", probes[0])["score"] == 2
    assert experiment.score_answer("I do not know.", probes[0])["score"] == 1
    conversation = json.loads((ROOT / "data" / "hw6_conversation_30.json").read_text())
    assert len(conversation) == 30


# ------------------------------------------------- Part 4: file memory


def sample_memory() -> str:
    return (ROOT / "memory_samples" / "MEMORY_original.md").read_text(encoding="utf-8")


def test_count_active_lines_ignores_comments_and_blanks():
    text = "<!-- a -->\n# T\n\n<!--\nmulti\n-->\n- k: v\n"
    assert file_memory.count_active_lines(text) == 2


def test_needs_consolidation_by_size_and_age():
    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    fresh = "<!-- last-consolidated: 2026-10-17T10:00:00+00:00 -->\n- a: b\n"
    assert file_memory.needs_consolidation(fresh, now)[0] is False
    old = "<!-- last-consolidated: 2026-10-15T10:00:00+00:00 -->\n- a: b\n"
    assert file_memory.needs_consolidation(old, now)[0] is True
    big = fresh + "".join(f"- key{i}: v\n" for i in range(41))
    assert file_memory.needs_consolidation(big, now)[0] is True
    assert file_memory.read_last_consolidated(fresh).hour == 10


def test_consolidation_of_the_55_line_memory_file():
    original = sample_memory()
    assert len(original.splitlines()) == 55
    fixed = file_memory.parse_fixed_facts((ROOT / "AGENT.md").read_text(encoding="utf-8"))
    result = file_memory.consolidate(original, datetime(2026, 10, 17, tzinfo=timezone.utc), fixed)
    assert result.lines_after < 40
    assert len(result.duplicates) >= 3 and len(result.contradictions) >= 3
    assert {item["key"] for item in result.incorrect} == {"port", "local_model"}
    for item in result.contradictions:  # nothing silently deleted
        for old in item["rejected"]:
            assert old.value in result.text
    assert "- port: 8333" in result.text and "8000" in result.text.split("## Resolved contradictions")[1]
    assert file_memory.needs_consolidation(result.text, datetime(2026, 10, 17, 1, tzinfo=timezone.utc))[0] is False


def test_commands(tmp_path):
    memory_path = tmp_path / "MEMORY.md"
    memory_path.write_text(sample_memory(), encoding="utf-8")
    agent_path = ROOT / "AGENT.md"
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)

    def chat_fn(messages):
        return '[{"key": "wedding_city", "value": "Portland"}, {"key": "port", "value": "8333"}]'

    assert "/compact" in file_memory.handle_command("/help", [], chat_fn, memory_path, agent_path, now)
    assert "consolidation needed: yes" in file_memory.handle_command("/memory", [], chat_fn, memory_path, agent_path, now)
    report = file_memory.handle_command("/compact", [], chat_fn, memory_path, agent_path, now)
    assert "Entries before: 49" in report and "after: 27" in report
    dream = file_memory.handle_command("/dream", [{"role": "user", "content": "My sister's wedding is in Portland."}], chat_fn, memory_path, agent_path, now)
    assert "wedding_city: Portland" in dream and "port: 8333" not in dream  # exact repeat skipped
    assert "wedding_city: Portland" in memory_path.read_text()
    assert "Unknown command" in file_memory.handle_command("/nope", [], chat_fn, memory_path, agent_path, now)


def test_agent_md_has_enough_instructions_in_enough_categories():
    text = (ROOT / "AGENT.md").read_text(encoding="utf-8")
    categories = ["Project description", "Technology stack", "Coding conventions", "Testing approach", "Prohibited actions"]
    counts = {}
    heading = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        elif line.startswith("- ") and heading in categories:
            counts[heading] = counts.get(heading, 0) + 1
    assert sum(counts.values()) >= 5 and len(counts) >= 3
    assert "You are a code review assistant." in text  # HW1 content kept


def test_system_prompt_contains_both_files():
    prompt = file_memory.build_system_prompt("AGENT TEXT", "MEMORY TEXT")
    assert "AGENT TEXT" in prompt and "MEMORY TEXT" in prompt
