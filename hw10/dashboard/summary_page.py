# ruff: noqa: E501
"""Summary page: request count, cache hit/miss, error rate, latency."""

import altair as alt
import pandas as pd
import streamlit as st

from hw10 import dash_data, stats

from hw10.dashboard import common


def render() -> None:
    """Draw the Summary page."""
    st.title("Summary")
    window_name = st.sidebar.selectbox("Time window", list(dash_data.WINDOWS), index=len(dash_data.WINDOWS) - 1)
    window = dash_data.WINDOWS[window_name]
    all_spans = common.spans()
    traces = dash_data.traces_in_window(all_spans, window)
    summary = stats.summary_metrics(traces)
    note = f"Window: {window_name} | Data source: span log, one `request` span per request (hit/miss from its `cache_lookup` span)"
    st.caption(note)

    if not summary["requests"]:
        st.info("No requests logged in this window yet. Run `python run_hw10_part4.py traces` first.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests", summary["requests"])
    c1.caption(f"Window: {window_name}. Source: `request` spans.")
    c2.metric("Cache hit rate", f"{summary['hit_rate_pct']}%")
    c2.caption(f"{summary['hits']} hits / {summary['misses']} misses. Source: `cache_lookup` spans (similarity >= threshold).")
    c3.metric("Error rate", f"{summary['error_rate_pct']}%")
    c3.caption(f"{summary['errors']} failed requests. Source: `request` span status.")
    c4.metric("p95 end-to-end latency", f"{summary['latency_all']['p95']:.0f} ms")
    c4.caption("All requests, request start to answer returned (evaluation not included).")

    def fmt(value, digits=0):
        """Number with ms, or a dash when this window has no such requests."""
        return "n/a" if value is None else f"{value:.{digits}f} ms"

    hit_p50 = summary["latency_hit"]["p50"]
    miss_p50 = summary["latency_miss"]["p50"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cache-hit p50", fmt(hit_p50, 1))
    m1.caption("Hit requests only. Source: `request` spans.")
    m2.metric("Cache-miss p50", fmt(miss_p50))
    m2.caption("Miss requests only. Source: `request` spans.")
    m3.metric("Hit vs miss speed-up", f"{miss_p50 / hit_p50:.0f}x" if hit_p50 and miss_p50 else "n/a")
    m3.caption("Miss p50 divided by hit p50.")
    m4.metric("Cache-miss p95", fmt(summary["latency_miss"]["p95"]))
    m4.caption("Miss requests only. Source: `request` spans.")

    st.subheader("Cache hits and misses")
    hm = pd.DataFrame({"path": ["hit", "miss"], "requests": [summary["hits"], summary["misses"]]})
    left, right = st.columns([1, 2])
    left.bar_chart(hm, x="path", y="requests", color="path")
    right.caption(f"Window: {window_name}. Source: `cache_lookup` spans. Hits and misses are separate latency populations; they are never averaged together below.")

    st.subheader("End-to-end latency (ms), hit and miss kept apart")
    lat = pd.DataFrame(
        [
            {"population": "Cache hit", "requests": summary["hits"], "p50 ms": summary["latency_hit"]["p50"], "p95 ms": summary["latency_hit"]["p95"]},
            {"population": "Cache miss", "requests": summary["misses"], "p50 ms": summary["latency_miss"]["p50"], "p95 ms": summary["latency_miss"]["p95"]},
            {"population": "All requests", "requests": summary["requests"], "p50 ms": summary["latency_all"]["p50"], "p95 ms": summary["latency_all"]["p95"]},
        ]
    )
    st.dataframe(lat, hide_index=True, width="stretch")
    st.caption(f"Window: {window_name}. Source: `request` span duration_ms (start of the request to the answer returned to the caller).")

    miss_traces = {t: s for t, s in traces.items() if any(x["stage"] == "evaluation" for x in s) and any(x["stage"] == "planner" for x in s)}
    if miss_traces:
        st.subheader("Where a cache miss spends its time")
        table = stats.miss_latency_table(miss_traces)
        st.dataframe(pd.DataFrame(table["rows"]).rename(columns={"p50_ms": "p50 (ms)", "p95_ms": "p95 (ms)", "share_pct": "% of miss end-to-end"}), hide_index=True, width="stretch")
        chart_rows = [r for r in table["rows"] if not r["stage"].startswith("End-to-end")]
        chart = pd.DataFrame({"stage": [r["stage"] for r in chart_rows], "% of miss end-to-end": [r["share_pct"] for r in chart_rows]})
        st.altair_chart(
            alt.Chart(chart).mark_bar(color="#e76f51").encode(
                y=alt.Y("stage:N", sort="-x", title=None),
                x=alt.X("% of miss end-to-end:Q", scale=alt.Scale(domain=[0, 100]), title="% of cache-miss end-to-end time"),
                tooltip=["stage", "% of miss end-to-end"],
            ).properties(height=260),
            width="stretch",
        )
        st.caption(
            f"Window: {window_name}. Source: stage spans of {table['n']} cache-miss traces that were also evaluated. "
            "End-to-end here includes the evaluation stage; the user-facing latency above does not."
        )

    pts = []
    for tid, items in traces.items():
        req = next((x for x in items if x["stage"] == "request"), None)
        if req:
            pts.append({"start": pd.to_datetime(req["start"]), "latency_ms": req["duration_ms"], "path": dash_data.tracing.trace_path(items)})
    if pts:
        st.subheader("Request latency over time")
        df = pd.DataFrame(pts).sort_values("start")
        st.altair_chart(
            alt.Chart(df).mark_circle(size=70, opacity=0.8).encode(
                x=alt.X("start:T", title="request start (UTC)"),
                y=alt.Y("latency_ms:Q", scale=alt.Scale(type="log"), title="latency (ms, log scale)"),
                color=alt.Color("path:N", scale=alt.Scale(domain=["hit", "miss"], range=["#2a9d8f", "#e76f51"]), title="path"),
                tooltip=["path", "latency_ms", "start"],
            ).properties(height=300),
            width="stretch",
        )
        st.caption(f"Window: {window_name}. Source: `request` spans. Teal is a cache hit, orange is a cache miss. The y-axis is logarithmic because hits take about 15 ms and misses about 7,000 ms.")

    st.subheader("Recent requests")
    rows = []
    for tid, items in list(traces.items())[-15:][::-1]:
        req = next((x for x in items if x["stage"] == "request"), None)
        if req:
            rows.append({"trace_id": tid, "path": dash_data.tracing.trace_path(items), "status": req["status"], "latency_ms": req["duration_ms"], "start": req["start"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"Window: {window_name}. Source: span log. Paste a trace_id on the Trace lookup page.")
