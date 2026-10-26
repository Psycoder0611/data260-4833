"""Offline tests for HW7 Part 4 (no Ollama, no network).

pytest test_hw7_bike_offline.py -q
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from hw7 import bike_agent, bike_costs, bike_run, bike_tools

FIXTURE = Path("reports/hw07/fixtures/bike_pricing_clean.txt").resolve()
URL = f"file://{FIXTURE}"
HEADER = [
    "ride_id", "rideable_type", "started_at", "ended_at", "start_station_name",
    "start_station_id", "end_station_name", "end_station_id", "start_lat",
    "start_lng", "end_lat", "end_lng", "member_casual", "synthetic_rider_id",
]  # fmt: skip


def make_csv(path: Path, heavy: bool) -> str:
    """40 rides for R001 (heavy) or 3 rides (light), plus 20 rows of other riders."""
    start = datetime(2026, 9, 1, 8, 0, 0)
    rows = []
    n_target = 40 if heavy else 3
    for i in range(n_target):
        s = start + timedelta(days=i * (28 // n_target), minutes=i)
        minutes = 30 + (i % 4) * 12 if heavy else 6 + i
        kind = "electric_bike" if i % 3 == 0 else "classic_bike"
        rows.append((s, minutes, kind, "R001"))
    for i in range(20):
        rows.append((start + timedelta(days=i, hours=3), 10, "classic_bike", "R002"))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HEADER)
        for n, (s, m, kind, rider) in enumerate(sorted(rows, key=lambda r: r[0])):
            e = s + timedelta(minutes=m)
            fmt = "%Y-%m-%d %H:%M:%S.000"
            w.writerow(
                [f"T{n}", kind, s.strftime(fmt), e.strftime(fmt), "", "", "", "",
                 "37.7", "-122.4", "37.7", "-122.4", "casual", rider]
            )  # fmt: skip
    return str(path)


def fetch_fixture(url: str) -> dict:
    from hw7 import bike_policy

    return bike_policy.fetch_page(url)


# --- tools -----------------------------------------------------------------


def test_calculator_is_whitelisted_and_safe():
    ok = bike_tools.calculator("(1.5+2)*4/2", units="USD")
    assert ok["success"] and ok["data"] == {"value": 7.0, "units": "USD"}
    for bad in ("__import__('os')", "2**3", "1+a", "", "1/0"):
        out = bike_tools.calculator(bad)
        assert out["success"] is False and "error" in out


def test_every_tool_returns_the_common_envelope(tmp_path):
    tools = bike_tools.BikeTools(make_csv(tmp_path / "t.csv", True), fetch_fixture)
    calls = [
        ("csv_sql", {"sql": "SELECT COUNT(*) AS n FROM rides"}),
        ("policy_retriever", {"url": URL, "query": "month pass price", "k": 3}),
        ("calculator", {"expression": "1+1"}),
        ("calculator", {"expression": "x"}),
        ("nope", {}),
    ]
    for name, inputs in calls:
        out = tools.call(name, inputs)
        assert isinstance(out["success"], bool) and "ts" in out
        assert ("data" in out) == out["success"] or "error" in out


def test_csv_sql_is_read_only(tmp_path):
    tools = bike_tools.BikeTools(make_csv(tmp_path / "t.csv", True), fetch_fixture)
    good = tools.call("csv_sql", {"sql": "SELECT COUNT(*) AS n FROM trips;"})
    assert good["data"]["rows"] == [{"n": 60}]
    assert good["data"]["source"] == "uploaded.csv"
    attacks = [
        "DROP TABLE trips",
        "DELETE FROM trips",
        "UPDATE trips SET ride_id='x'",
        "SELECT 1; DROP TABLE trips",
        "SELECT 1 -- hi",
        "PRAGMA table_info(trips)",
        "ATTACH DATABASE 'x.db' AS x",
        "WITH t AS (SELECT 1) DELETE FROM trips",
    ]
    for sql in attacks:
        assert tools.call("csv_sql", {"sql": sql})["success"] is False, sql
    count = tools.call("csv_sql", {"sql": "SELECT COUNT(*) AS n FROM trips"})
    assert count["data"]["rows"] == [{"n": 60}]


def test_database_layer_blocks_writes_even_without_the_text_check(tmp_path):
    import sqlite3

    db = bike_tools.TripDB(make_csv(tmp_path / "t.csv", True))
    with pytest.raises(sqlite3.DatabaseError):
        db.conn.execute("DELETE FROM trips")


def test_undefended_database_can_be_modified(tmp_path):
    """The 'before' state used in Part 5 (never the default)."""
    db = bike_tools.TripDB(make_csv(tmp_path / "t.csv", True), read_only=False)
    db.query("DELETE FROM trips WHERE synthetic_rider_id = 'R002'; SELECT 1")
    left = db.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    assert left == 40


def test_csv_sql_caps_rows(tmp_path):
    tools = bike_tools.BikeTools(make_csv(tmp_path / "t.csv", True), fetch_fixture)
    out = tools.call("csv_sql", {"sql": "SELECT ride_id FROM trips"})
    assert out["data"]["row_count"] == bike_tools.MAX_ROWS
    assert out["data"]["truncated"] is True


def test_policy_retriever_finds_the_month_pass_lines():
    out = bike_tools.policy_retriever(
        URL, "single ride month pass price unlock free minutes", 10, fetch_fixture
    )
    texts = [p["text"] for p in out["data"]["passages"]]
    assert "Month pass: $29/month" in texts
    assert "Classic bike - Month pass: 45 min free, then $0.17/min" in texts
    assert "Ebike - Single ride: $1.00 unlock + $0.49/min" in texts
    for p in out["data"]["passages"]:
        assert p["source"] == URL and len(p["text"]) <= 240 and p["score"] > 0


def test_policy_retriever_reports_a_bad_url():
    out = bike_tools.policy_retriever("file:///no/such/page", "month", 3, fetch_fixture)
    assert out["success"] is False and "fetch failed" in out["error"]


def test_schemas_cover_all_three_tools():
    schemas = bike_tools.tool_schemas()
    assert set(schemas) == {"csv_sql", "policy_retriever", "calculator"}
    assert schemas["policy_retriever"]["input"]["required"] == ["url", "query"]
    assert "rows" in schemas["csv_sql"]["output"]["properties"]["data"]["properties"]


# --- agent -----------------------------------------------------------------

SQL = (
    "SELECT week, COUNT(*) AS rides, ROUND(AVG(duration_min),1) AS avg_min, "
    "ROUND(SUM(1.00 + CASE WHEN is_ebike=1 THEN 0.49*duration_min "
    "ELSE 0.19*duration_min END),2) AS pay_spend, "
    "ROUND(SUM(CASE WHEN is_ebike=1 THEN 0.17*duration_min "
    "ELSE 0.17*MAX(duration_min-45,0) END),2) AS member_extra "
    "FROM rides WHERE synthetic_rider_id='R001' GROUP BY week ORDER BY week"
)


def scripted_model(script_errors=None):
    """A fake model that follows the six steps using the real tool results."""
    script_errors = list(script_errors or [])
    seen = {"rows": None}

    def chat(messages, temperature=0.0, seed=0):
        if script_errors:
            return reply(script_errors.pop(0))
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        n = len(tool_msgs)
        if n >= 2 and seen["rows"] is None:
            seen["rows"] = json.loads(tool_msgs[1]["content"])["data"]["rows"]
        rows = seen["rows"]
        if n == 0:
            d = tool("policy_retriever", url=URL, k=10, query="single ride month pass")
        elif n == 1:
            d = tool("csv_sql", sql=SQL)
        elif n == 2:
            d = tool(
                "calculator", expression="+".join(str(r["pay_spend"]) for r in rows)
            )
        elif n == 3:
            extra = "+".join(str(r["member_extra"]) for r in rows)
            d = tool("calculator", expression=f"29+{extra}")
        elif n == 4:
            pay = json.loads(tool_msgs[2]["content"])["data"]["value"]
            rides = sum(r["rides"] for r in rows)
            d = tool("calculator", expression=f"29*{rides}/{pay}")
        else:
            pay = json.loads(tool_msgs[2]["content"])["data"]["value"]
            mem = json.loads(tool_msgs[3]["content"])["data"]["value"]
            be = json.loads(tool_msgs[4]["content"])["data"]["value"]
            who = "Buy Monthly Membership" if mem < pay else "Pay Per Ride/Minute"
            d = {
                "action": "final",
                "answer": {
                    "decision": who,
                    "pay_per_use_total": pay,
                    "membership_total": mem,
                    "break_even_rides": be,
                    "justification": (
                        "Month pass: $29/month is the fee. The calculator gave "
                        "both totals. The lower total wins."
                    ),
                    "assumptions": ["minutes are not rounded up"],
                },
            }
        return reply(json.dumps(d))

    return chat


def tool(name, **inputs):
    return {"thought": "next", "action": "tool", "tool": name, "inputs": inputs}


def reply(content):
    if not isinstance(content, str):
        content = json.dumps(content)
    return {"content": content, "input_tokens": 10, "output_tokens": 5, "latency_ms": 1}


@pytest.mark.parametrize(
    "heavy,expected",
    [(True, "Buy Monthly Membership"), (False, "Pay Per Ride/Minute")],
)
def test_agent_decides_and_matches_the_reference(tmp_path, heavy, expected):
    csv_path = make_csv(tmp_path / "t.csv", heavy)
    events = []
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", on_event=events.append,
        chat_fn=scripted_model(), fetch=fetch_fixture, raw_dir=tmp_path,
    )  # fmt: skip
    assert result["stop_reason"] == "final_answer" and result["steps"] == 6
    assert result["decision"] == expected
    assert all(result["checks"].values()), result["checks"]
    assert result["membership_fee"] == 29.0
    assert result["actual_rides"] == (40 if heavy else 3)
    assert [e["kind"] for e in events] == ["tool"] * 5 + ["final"]
    assert result["citations"][0]["url"] == URL
    saved = json.loads((tmp_path / "pricing_snapshot_t.json").read_text())
    assert saved["sha256"] == result["citations"][0]["sha256"]
    assert (tmp_path / "pricing_snapshot_t.txt").exists()
    assert (tmp_path / "bike_t_run.json").exists()


def test_agent_repairs_a_bad_reply_then_finishes(tmp_path):
    csv_path = make_csv(tmp_path / "t.csv", True)
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture,
        chat_fn=scripted_model(["I think you should buy it."]),
    )  # fmt: skip
    assert result["stop_reason"] == "final_answer"
    assert result["repairs"] == 1 and result["steps"] == 7


def test_agent_rejects_a_final_answer_before_the_tools(tmp_path):
    early = {
        "action": "final",
        "answer": {
            "decision": "Buy Monthly Membership", "pay_per_use_total": 1,
            "membership_total": 1, "break_even_rides": 1, "justification": "x",
        },
    }  # fmt: skip
    csv_path = make_csv(tmp_path / "t.csv", True)
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture,
        chat_fn=scripted_model([early]),
    )  # fmt: skip
    assert result["repairs"] == 1 and result["stop_reason"] == "final_answer"


def test_agent_stops_after_repeated_bad_replies(tmp_path):
    csv_path = make_csv(tmp_path / "t.csv", True)
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture,
        chat_fn=scripted_model(["nope", "still nope", "no"]),
    )  # fmt: skip
    assert result["stop_reason"] == "repair_failed" and result["decision"] is None


def test_agent_stops_at_the_step_limit(tmp_path):
    csv_path = make_csv(tmp_path / "t.csv", True)
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture,
        chat_fn=scripted_model(), max_steps=3,
    )  # fmt: skip
    assert result["stop_reason"] == "max_steps" and result["steps"] == 3


def test_final_numbers_must_come_from_the_calculator(tmp_path):
    def liar(messages, temperature=0.0, seed=0):
        out = scripted_model()(messages, temperature, seed)
        d = json.loads(out["content"])
        if d["action"] == "final":
            d["answer"]["membership_total"] = 1.0
            out["content"] = json.dumps(d)
        return out

    csv_path = make_csv(tmp_path / "t.csv", False)
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture, chat_fn=liar
    )
    assert result["stop_reason"] == "repair_failed" and result["decision"] is None
    assert result["repairs"] == 3


def test_missing_step_is_named_in_the_rejection(tmp_path):
    csv_path = make_csv(tmp_path / "t.csv", True)
    sent = []
    base = scripted_model()

    def chat(messages, temperature=0.0, seed=0):
        sent.append(messages)
        if len([m for m in messages if m["role"] == "tool"]) == 4:
            return reply({"action": "final", "answer": {}})
        return base(messages, temperature, seed)

    bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture, chat_fn=chat
    )
    problems = [m["content"] for m in sent[-1] if m["content"].startswith("Problem")]
    assert any("step 5" in p and "break-even" in p for p in problems)


def test_reference_matches_hand_calculation(tmp_path):
    csv_path = make_csv(tmp_path / "t.csv", False)
    ref = bike_costs.reference(csv_path, "R001")
    # 3 rides of 6, 7, 8 minutes: ebike 6 min, classic 7 and 8 min
    assert ref["pay_total"] == round(3 * 1.0 + 0.49 * 6 + 0.19 * 15, 2)
    assert ref["decision"] == bike_costs.DECISION_PAY


def test_check_final_rejects_bad_answers():
    good = {
        "decision": "Pay Per Ride/Minute", "pay_per_use_total": 1.0,
        "membership_total": 30, "break_even_rides": 9, "justification": "ok",
    }  # fmt: skip
    assert bike_agent.check_final(good) is None
    assert bike_agent.check_final({**good, "decision": "maybe"})
    assert bike_agent.check_final({**good, "pay_per_use_total": "1"})
    assert bike_agent.check_final(
        {k: v for k, v in good.items() if k != "justification"}
    )


def test_justification_needs_three_sentences_and_a_quote(tmp_path):
    def terse(messages, temperature=0.0, seed=0):
        out = scripted_model()(messages, temperature, seed)
        d = json.loads(out["content"])
        if d["action"] == "final":
            d["answer"]["justification"] = "Membership is cheaper."
            out["content"] = json.dumps(d)
        return out

    def no_quote(messages, temperature=0.0, seed=0):
        out = scripted_model()(messages, temperature, seed)
        d = json.loads(out["content"])
        if d["action"] == "final":
            d["answer"]["justification"] = "It is cheaper. Really. Trust me."
            out["content"] = json.dumps(d)
        return out

    csv_path = make_csv(tmp_path / "t.csv", True)
    for chat, text in ((terse, "3-6 sentences"), (no_quote, "quote at least one")):
        sent = []

        def spy(messages, temperature=0.0, seed=0, chat=chat):
            sent.append(messages)
            return chat(messages, temperature, seed)

        result = bike_run.run_scenario(
            csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture, chat_fn=spy
        )
        assert result["stop_reason"] == "repair_failed"
        assert any(text in m["content"] for m in sent[-1])


def test_decision_must_follow_the_totals(tmp_path):
    def flipped(messages, temperature=0.0, seed=0):
        out = scripted_model()(messages, temperature, seed)
        d = json.loads(out["content"])
        if d["action"] == "final":
            d["answer"]["decision"] = "Buy Monthly Membership"
            out["content"] = json.dumps(d)
        return out

    sent = []

    def spy(messages, temperature=0.0, seed=0):
        sent.append(messages)
        return flipped(messages, temperature, seed)

    csv_path = make_csv(tmp_path / "t.csv", False)  # pay per ride is cheaper
    result = bike_run.run_scenario(
        csv_path, "R001", URL, "t", save=False, fetch=fetch_fixture, chat_fn=spy
    )
    assert result["stop_reason"] == "repair_failed" and result["decision"] is None
    assert any(
        "'decision' must be 'Pay Per Ride/Minute'" in m["content"] for m in sent[-1]
    )
