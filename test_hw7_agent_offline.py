"""Offline tests for the HW7 Part 2 agent loop (scripted fake model, no Ollama)."""

import json

from hw7 import agent


def scripted(replies):
    """Fake chat_fn that returns the given replies in order."""
    queue = list(replies)
    seen = []

    def chat_fn(messages):
        seen.append([dict(m) for m in messages])
        return {"content": queue.pop(0), "input_tokens": 10, "output_tokens": 5}

    chat_fn.seen = seen
    return chat_fn


def fake_execute(name, inputs):
    if name == "get_trial_details" and inputs.get("trial_id") == 999999:
        return json.dumps(
            {"ok": False, "data": None, "error": "Clinical trial not found"}
        )
    return json.dumps({"ok": True, "data": {"echo": name}, "error": None})


def tool(name, **inputs):
    return json.dumps({"action": "tool", "tool": name, "inputs": inputs})


def final(text="done"):
    return json.dumps({"action": "final", "answer": text})


def run(replies, **kwargs):
    return agent.run_agent(
        "q", chat_fn=scripted(replies), execute=fake_execute, log_path=None, **kwargs
    )


def test_two_step_chain_with_tool_role_messages():
    chat_fn = scripted(
        [
            tool("search_trials", query="Cardio"),
            tool("get_trial_details", trial_id=5006),
            final(),
        ]
    )
    result = agent.run_agent("q", chat_fn=chat_fn, execute=fake_execute, log_path=None)
    assert result["stop_reason"] == "final_answer"
    assert result["tool_calls"] == 2
    assert result["first_try_ok"] == result["call_attempts"] == 2
    roles = [m["role"] for m in chat_fn.seen[-1]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool"]


def test_unknown_tool_is_repaired_once():
    result = run([tool("delete_everything"), tool("search_trials", query="a"), final()])
    assert result["failures"] == [agent.UNKNOWN_TOOL]
    assert result["repair_attempts"] == 1 and result["repair_ok"] == 1
    assert result["first_try_ok"] == 0 and result["call_attempts"] == 1
    assert result["stop_reason"] == "final_answer"


def test_malformed_arguments_get_specific_message():
    chat_fn = scripted(
        [
            tool("get_trial_details", trial_id="12"),
            tool("get_trial_details", trial_id=12),
            final(),
        ]
    )
    result = agent.run_agent("q", chat_fn=chat_fn, execute=fake_execute, log_path=None)
    assert result["failures"] == [agent.MALFORMED]
    repair_msg = chat_fn.seen[1][-1]["content"]
    assert "'trial_id' must be an integer" in repair_msg


def test_text_when_tool_required():
    result = run(
        ["Sure, I know the answer!", tool("search_trials", query="x"), final()]
    )
    assert result["failures"] == [agent.TEXT_INSTEAD]
    assert result["tool_calls"] == 1


def test_final_before_any_tool_is_rejected():
    result = run(
        [final("guess"), tool("organization_trial_summary", organization_id=2), final()]
    )
    assert result["failures"] == [agent.TEXT_INSTEAD]
    assert result["tool_calls"] == 1


def test_failed_repairs_stop_cleanly():
    result = run(["nope", "still nope", "nope again", "nope 4"], max_failed_repairs=2)
    assert result["stop_reason"] == "repair_failed"
    assert result["tool_calls"] == 0


def test_repair_off_stops_on_first_bad_reply():
    result = run(["nope"], repair=False)
    assert result["stop_reason"] == "rejected_no_repair"
    assert result["repair_attempts"] == 0


def test_iteration_ceiling():
    result = run([tool("search_trials", query="a")] * 4, max_iterations=3)
    assert result["stop_reason"] == "max_iterations"
    assert result["tool_calls"] == 3


def test_nonexistent_id_does_not_crash():
    result = run(
        [
            tool("get_trial_details", trial_id=999999),
            final("Trial 999999 was not found."),
        ]
    )
    assert result["tool_log"][0]["ok"] is False
    assert result["tool_log"][0]["error"] == "Clinical trial not found"
    assert result["stop_reason"] == "final_answer"


def test_model_error_is_contained():
    def boom(messages):
        raise RuntimeError("ollama down")

    result = agent.run_agent("q", chat_fn=boom, execute=fake_execute, log_path=None)
    assert result["stop_reason"] == "model_error"


def test_parse_decision_handles_fences_and_prose():
    text = 'Here you go:\n```json\n{"action": "final", "answer": "x"}\n```'
    assert agent.parse_decision(text) == {"action": "final", "answer": "x"}
    assert agent.parse_decision("no json here") is None


def test_validate_inputs_rules():
    assert (
        agent.validate_inputs("search_trials", {"query": "a", "limit": 30}) is not None
    )
    assert (
        agent.validate_inputs("search_trials", {"query": "a", "extra": 1}) is not None
    )
    assert agent.validate_inputs("get_trial_details", {"trial_id": True}) is not None
    assert agent.validate_inputs("get_trial_details", {"trial_id": 0}) is not None
    assert (
        agent.validate_inputs("organization_trial_summary", {"organization_id": 2})
        is None
    )


# ---------------------------------------------------------------- cases


def test_case_chain_and_answer_checks():
    from hw7 import cases

    case_c = cases.get_case("C")
    log = [
        {"tool": "search_trials", "inputs": {"query": "x"}},
        {"tool": "get_trial_details", "inputs": {"trial_id": 5011}},
    ]
    assert not cases.chain_ok(case_c, log)  # only one detail lookup
    log.append({"tool": "get_trial_details", "inputs": {"trial_id": 5011}})
    assert not cases.chain_ok(case_c, log)  # same id twice is not two entities
    log[-1]["inputs"] = {"trial_id": 5014}
    assert cases.chain_ok(case_c, log)
    assert cases.answer_ok(case_c, "Diabetes study is larger: 200 vs 90.")
    assert not cases.answer_ok(case_c, None)


def test_reliability_summary_rates_and_classes():
    from hw7 import reliability

    rows = [
        {
            "case": "A",
            "call_attempts": 3,
            "first_try_ok": 2,
            "repair_ok": 1,
            "failures": ["unknown_tool"],
            "chain_ok": True,
            "answer_ok": True,
            "tool_calls": 2,
            "tokens": 100,
            "model_latency_ms": 10.0,
        },
        {
            "case": "B",
            "call_attempts": 2,
            "first_try_ok": 1,
            "repair_ok": 0,
            "failures": ["malformed_arguments"],
            "chain_ok": False,
            "answer_ok": False,
            "tool_calls": 1,
            "tokens": 50,
            "model_latency_ms": 20.0,
        },
    ]
    summary = reliability.summarize(rows)
    assert summary["rate_before_repair"] == 0.6
    assert summary["rate_after_repair"] == 0.8
    assert summary["failures_by_class"]["lost_multi_step_chain"] == 1
    assert summary["failures_by_class"]["unknown_tool"] == 1


def test_fault_injector_rotates_and_skips_repair_replies():
    from hw7 import reliability

    injector = reliability.FaultInjector(1)
    good = tool("get_trial_details", trial_id=5011)
    plain = [{"role": "user", "content": "q"}]
    first = injector.maybe_corrupt(plain, good)
    assert json.loads(first)["tool"] == "find_trials"
    second = injector.maybe_corrupt(plain, good)
    assert agent.validate_inputs("get_trial_details", json.loads(second)["inputs"])
    third = injector.maybe_corrupt(plain, good)
    assert agent.parse_decision(third) is None
    repair = [{"role": "user", "content": "Your last reply was rejected: x"}]
    assert injector.maybe_corrupt(repair, good) == good
    assert injector.maybe_corrupt(plain, final()) == final()
    assert injector.injected == 3
