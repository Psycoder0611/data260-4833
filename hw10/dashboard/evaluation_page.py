# ruff: noqa: E501
"""Evaluation page: Part 2 scores per stage and case, Part 3 judge validation."""

import altair as alt
import pandas as pd
import streamlit as st

from hw10 import dash_data

from hw10.dashboard import common


def _case_rows(records):
    """Flat rows for the per-case table."""
    return [
        {
            "trace_id": r["trace_id"],
            "source": r.get("source", ""),
            "question": (r["question"] or "")[:70],
            "plan quality": r["plan_quality"]["score"],
            "draft helpfulness": r["writer_helpfulness"]["score"],
            "final helpfulness": r["final_helpfulness"]["score"],
            "final - draft": r["improvement"]["difference"],
            "reviewer": f"{(r.get('reviewer') or {}).get('status')} {(r.get('reviewer') or {}).get('score')}/10",
            "status": r["status"],
        }
        for r in records
    ]


def render() -> None:
    """Draw the Evaluation page."""
    st.title("Evaluation")
    records = dash_data.evaluation_records()

    st.header("Part 2: scores by pipeline stage and case")
    st.caption("Window: all evaluated requests in the result files. Data source: part2_eval.json and part4_latency_runs.jsonl (judge: local qwen3:8b through DeepEval GEval, scale 1-5).")
    if not records:
        st.info("No evaluation records yet. Run `python run_hw10_part2.py` first.")
    else:
        means = dash_data.stage_means(records)
        chart = pd.DataFrame({"stage": list(means), "mean score": [v or 0 for v in means.values()]})
        st.altair_chart(
            alt.Chart(chart).mark_bar().encode(x=alt.X("stage:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=260)), y=alt.Y("mean score:Q", scale=alt.Scale(domain=[0, 5])), tooltip=["stage", "mean score"]).properties(height=260),
            width="stretch",
        )
        st.caption(f"Mean over {len(records)} evaluated traces. Source: evaluator records.")
        table = pd.DataFrame(_case_rows(records))
        st.dataframe(table, hide_index=True, width="stretch")
        pick = st.selectbox("Open one case (reasons from the judge)", [r["trace_id"] for r in records])
        rec = next(r for r in records if r["trace_id"] == pick)
        st.markdown(f"**Question:** {rec['question']}")
        st.markdown(f"**Plan Quality {rec['plan_quality']['score']}/5:** {rec['plan_quality']['reason']}")
        st.markdown(f"**Writer Helpfulness {rec['writer_helpfulness']['score']}/5** (trace_id `{rec['writer_helpfulness']['trace_id']}`): {rec['writer_helpfulness']['reason']}")
        st.markdown(f"**Final Answer Helpfulness {rec['final_helpfulness']['score']}/5:** {rec['final_helpfulness']['final_answer']}")
        imp = rec["improvement"]
        st.markdown(f"**Final vs Draft:** draft {imp['draft_score']}, final {imp['final_score']}, difference {imp['difference']}. {imp['interpretation']}")
        st.subheader("How Planner, Writer and Reviewer worked together")
        st.write(dash_data.coordination_text(records))

    st.header("Part 3: judge validation")
    st.caption("Data source: part3_validation.json (20 Writer drafts, human labels vs the local judge; 3 repeated runs).")
    val = common.raw_json("part3_validation.json")
    if not val:
        st.info("Judge validation has not been run yet (`python run_hw10_part3.py all`).")
        return
    v = val["validation"]
    a, b, c, d = st.columns(4)
    a.metric("Spearman (human vs judge)", v["spearman"])
    b.metric("Mean absolute difference", v["mad"])
    c.metric("Scores that changed between runs", f"{val['repeatability']['fraction_changed'] * 100:.0f}%")
    d.metric("Max change between runs", val["repeatability"]["max_abs_change"])
    st.caption(
        f"n={v['n']} cases scored. Validation uses run {val['validation_run']} of {val['repeatability']['runs']}; repeatability compares all runs "
        f"(mean change {val['repeatability']['mean_abs_change']})."
    )
    rows = pd.DataFrame(val["cases"])
    st.dataframe(rows, hide_index=True, width="stretch")
    grid = rows.dropna(subset=["judge_run1"]).groupby(["human_score", "judge_run1"]).size().reset_index(name="cases")
    base = alt.Chart(grid).encode(
        x=alt.X("human_score:O", title="human label (1-5)", sort=[1, 2, 3, 4, 5], axis=alt.Axis(labelAngle=0)),
        y=alt.Y("judge_run1:O", title="judge score, run 1 (1-5)", sort=[5, 4, 3, 2, 1]),
    )
    heat = base.mark_rect(cornerRadius=4).encode(color=alt.Color("cases:Q", scale=alt.Scale(scheme="blues"), legend=None), tooltip=["human_score", "judge_run1", "cases"])
    text = base.mark_text(fontSize=16, fontWeight="bold").encode(text="cases:Q", color=alt.value("white"))
    st.altair_chart((heat + text).properties(height=300), width="stretch")
    st.caption("Each cell counts cases with that human label (x) and judge score (y). The diagonal is exact agreement; the judge sits above the diagonal when it is more generous than the human.")
