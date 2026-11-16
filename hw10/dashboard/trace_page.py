# ruff: noqa: E501
"""Trace lookup page: the full journey of one trace_id in stage order."""

import altair as alt
import pandas as pd
import streamlit as st

from hw10 import dash_data, tracing

from hw10.dashboard import common


def render() -> None:
    """Draw the Trace lookup page."""
    st.title("Trace lookup")
    all_spans = common.spans()
    traces = tracing.group_by_trace(all_spans)
    named = common.raw_json("part4_traces.json") or {}
    shortcuts = {f"{label} trace": info["trace_id"] for label, info in named.get("traces", {}).items()}
    if shortcuts:
        st.caption("Named traces from my Part 4 run: " + ", ".join(f"{k} = `{v}`" for k, v in shortcuts.items()))
    choice = st.selectbox("Pick a named trace (optional)", ["(type an id below)"] + list(shortcuts))
    typed = st.text_input("trace_id (the HW8 correlation_id)", value="" if choice.startswith("(") else shortcuts[choice])
    trace_id = typed.strip()
    st.caption("Data source: span log (one JSON span per stage, trace_id = correlation_id).")
    if not trace_id:
        st.info("Enter a trace_id.")
        return
    spans = traces.get(trace_id)
    if not spans:
        st.error(f"No spans found for trace_id {trace_id!r}.")
        return

    status = tracing.trace_status(spans)
    kind = tracing.trace_path(spans)
    (st.success if status == "ok" else st.error)(f"Trace {trace_id}: path = {kind.upper()}, request status = {status}")
    st.write(dash_data.path_description(spans))
    failing = tracing.failing_stage(spans)
    if failing and status == "error":
        st.warning(f"Failing stage: **{failing['stage']}** - {failing['error']}")

    table = pd.DataFrame(dash_data.span_table(spans))
    st.dataframe(table, hide_index=True, width="stretch")

    t0 = min(tracing.parse_iso(s["start"]) for s in spans)
    gantt = pd.DataFrame(
        [
            {"stage": s["stage"], "from_ms": (tracing.parse_iso(s["start"]) - t0) * 1000, "to_ms": (tracing.parse_iso(s["end"]) - t0) * 1000 + 0.5, "status": s["status"]}
            for s in dash_data.stage_sorted(spans) if s["stage"] != tracing.REQUEST
        ]
    )
    st.altair_chart(
        alt.Chart(gantt).mark_bar().encode(
            y=alt.Y("stage:N", sort=None), x=alt.X("from_ms:Q", title="ms since the first span", scale=alt.Scale(domain=[0, float(gantt["to_ms"].max()) * 1.05], nice=False)), x2="to_ms:Q",
            color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error"], range=["#2f6fb0", "#c0392b"])),
            tooltip=["stage", "from_ms", "to_ms", "status"],
        ).properties(height=max(120, 40 + 28 * len(gantt))),
        width="stretch",
    )
    evals = [r for r in dash_data.evaluation_records() if r["trace_id"] == trace_id]
    if evals:
        rec = evals[0]
        st.subheader("Evaluator result for this trace")
        st.write(f"Plan quality {rec['plan_quality']['score']}/5 | draft helpfulness {rec['writer_helpfulness']['score']}/5 | final helpfulness {rec['final_helpfulness']['score']}/5 | {rec['improvement']['interpretation']}")
