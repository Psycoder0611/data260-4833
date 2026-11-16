# ruff: noqa: E501
"""HW10 Streamlit dashboard: Summary, Evaluation and Trace lookup.

    streamlit run hw10_dashboard.py

Everything shown comes from my own logs and result files under reports/hw10/raw/
(see hw10/dash_data.py); each metric says which file and which time window it uses.
"""

import streamlit as st

from hw10.dashboard import evaluation_page, summary_page, trace_page

st.set_page_config(page_title="HW10 pipeline dashboard", layout="wide")
st.sidebar.caption("Student: Trapti Kulshrestha | SID4 4833 | HW10 dashboard")

pages = [
    st.Page(summary_page.render, title="Summary", url_path="summary", default=True),
    st.Page(evaluation_page.render, title="Evaluation", url_path="evaluation"),
    st.Page(trace_page.render, title="Trace lookup", url_path="trace"),
]
st.navigation(pages).run()
