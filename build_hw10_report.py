# ruff: noqa: E501
"""Build the HW10 report (Word + PDF) from the raw files of my runs.

  python build_hw10_report.py                  Git copy: Report_editable.docx + Report.pdf
  python build_hw10_report.py --commit <hash>  also the Canvas copy:
                                               Kulshrestha_HW10_editable.docx + Kulshrestha_HW10.pdf
                                               (adds the tag hw10 and the commit hash)
  python build_hw10_report.py --list-screenshots

The text is written by me. Numbers in the tables are read from reports/hw10/raw/
(part2_eval.json, part3_validation.json, part4_latency.json, part4_traces.json,
part4_latency_runs.jsonl, spans.jsonl). Code excerpts are cut out of the real source files,
so they cannot drift from the code. Screenshots are in reports/hw10/screenshots/ (not in git).
"""

import argparse
import ast
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from scipy.stats import spearmanr

from hw10 import config, dash_data, stats

ROOT = Path(__file__).resolve().parent
OUT = Path(config.REPORT_DIR)
RAW = Path(config.RAW_DIR)
SHOTS = OUT / "screenshots"
REPO_URL = "https://github.com/Psycoder0611/data260-4833"
PENDING = "[not available]"
FONT = "Calibri"

FIGS = {
    "agent_planner": ("Planner agent running (python hw10_agents.py planner)", "Terminal: the Planner, with the name banner."),
    "agent_writer": ("Writer agent running (python hw10_agents.py writer)", "Terminal: the Writer."),
    "agent_reviewer": ("Reviewer agent running (python hw10_agents.py reviewer)", "Terminal: the Reviewer."),
    "code_common": ("Code: SpanSource, get_source and load_spans (hw10/dashboard/common.py)", "VS Code: hw10/dashboard/common.py lines 22-47."),
    "code_score_text": ("Code: score_text, the bounded judge call (hw10/judge.py)", "VS Code: hw10/judge.py lines 199-233."),
    "code_tracing": ("Code: make_span and emit (hw10/tracing.py)", "VS Code: hw10/tracing.py lines 74-107."),
    "code_traced": ("Code: traced, the wrapper that writes a span for every attempt (hw10/kafka_trace.py)", "VS Code: hw10/kafka_trace.py lines 47-81."),
    "tests": ("Offline tests: 11 passed (make test-hw10)", "Terminal: make test-hw10."),
    "dash_summary_top": ("Dashboard, Summary page: metrics, cache hits and misses, latency table", "Browser: Summary page, top."),
    "dash_summary_charts": ("Dashboard, Summary page: where a cache miss spends its time, latency over time", "Browser: Summary page scrolled down."),
    "dash_eval_top": ("Dashboard, Evaluation page: Part 2 scores by stage and case", "Browser: Evaluation page, top."),
    "dash_eval_bottom": ("Dashboard, Evaluation page: coordination text and Part 3 judge validation", "Browser: Evaluation page, bottom."),
    "part2_run": ("Part 2 run: three questions through the pipeline and the evaluator", "Terminal: python run_hw10_part2.py."),
    "cases_made": ("make_hw10_cases.py: the 20 questions and Writer drafts", "Terminal: python make_hw10_cases.py."),
    "label_prompt": ("Labeling a draft by hand (label_hw10_cases.py, case C01)", "Terminal: label_hw10_cases.py prompt."),
    "label_commit": ("Labels finished and committed before any judge score existed", "Terminal: end of labeling plus the commit."),
    "part3_start": ("Part 3 judge run 1 and 2 (inputs committed in 0befa57f63)", "Terminal: start of python run_hw10_part3.py all."),
    "part3_end": ("Part 3 judge run 3 and the statistics block", "Terminal: end of python run_hw10_part3.py all."),
    "part4_traces": ("Part 4: the cache-miss, cache-hit and failed trace as printed by run_hw10_part4.py traces", "Terminal: python run_hw10_part4.py traces."),
    "trace_miss": ("Trace lookup: the successful cache-miss trace", "Browser: Trace lookup, miss id."),
    "trace_hit": ("Trace lookup: the cache-hit trace", "Browser: Trace lookup, hit id."),
    "trace_failed": ("Trace lookup: the failed trace (failing stage: writer)", "Browser: Trace lookup, failed id."),
    "part4_latency": ("Part 4.3: 50 confirmed cache-miss requests and the stage table", "Terminal: python run_hw10_part4.py latency --n 50."),
    "part4_hits": ("Part 4.3: 20 repeated questions, all cache hits", "Terminal: python run_hw10_part4.py hits --n 20."),
    "verify": ("make verify-hw10: all checks pass", "Terminal: pytest and make verify-hw10."),
}  # fmt: skip

ORDER = [
    "agent_planner", "agent_writer", "agent_reviewer", "tests",
    "dash_summary_top", "dash_summary_charts", "dash_eval_top", "dash_eval_bottom", "code_common",
    "code_score_text", "part2_run",
    "cases_made", "label_prompt", "label_commit", "part3_start", "part3_end",
    "code_tracing", "code_traced", "part4_traces", "trace_miss", "trace_hit", "trace_failed", "part4_latency", "part4_hits",
    "verify",
]  # fmt: skip
PLACED: List[str] = []


# --------------------------------------------------------------------- helpers
def fig_no(key: str) -> int:
    """Figure number of a screenshot key (position in the report)."""
    return ORDER.index(key) + 1


def ref(*keys: str) -> str:
    """'Figure 3' or 'Figures 3 and 4' for the given keys."""
    nums = [fig_no(k) for k in keys]
    if len(nums) == 1:
        return f"Figure {nums[0]}"
    return "Figures " + ", ".join(str(n) for n in nums[:-1]) + f" and {nums[-1]}"


def load(name: str) -> Optional[Any]:
    """Load a raw JSON file, or None."""
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def short(text: str, n: int = 70) -> str:
    """Cut a long text for a table cell."""
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def source_of(path: str, *names: str) -> str:
    """Exact source text of functions (or Class.method) cut from a file of the repo."""
    text = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    parts = []
    for name in names:
        node: Any = tree
        for piece in name.split("."):
            node = next(n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == piece)
        parts.append(ast.get_source_segment(text, node))
    return "\n\n".join(parts)


# ------------------------------------------------------------------- docx tools
class Doc:
    """Small wrapper that keeps the formatting rules in one place."""

    def __init__(self) -> None:
        """Create the document with Calibri 11 pt body text."""
        self.d = Document()
        section = self.d.sections[0]
        section.left_margin = section.right_margin = Inches(0.9)
        section.top_margin = section.bottom_margin = Inches(0.8)
        style = self.d.styles["Normal"]
        style.font.name = FONT
        style.font.size = Pt(11)
        style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.space_after = Pt(6)

    def _run(self, p, text: str, size: float, bold: bool = False, mono: bool = False, color: Optional[str] = None, italic: bool = False):
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold
        run.italic = italic
        run.font.name = "Consolas" if mono else FONT
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        return run

    def title(self, text: str) -> None:
        """Big centred title."""
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._run(p, text, 24)

    def centered(self, text: str, size: float = 13) -> None:
        """Centred line of text."""
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._run(p, text, size, color="555555")

    def h1(self, text: str) -> None:
        """Main heading: 14 pt bold."""
        p = self.d.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.keep_with_next = True
        self._run(p, text, 14, bold=True)

    def h2(self, text: str) -> None:
        """Subheading: 12 pt bold."""
        p = self.d.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        self._run(p, text, 12, bold=True)

    def p(self, text: str) -> None:
        """Body paragraph: 11 pt."""
        p = self.d.add_paragraph()
        self._run(p, text, 11)

    def label(self, label: str, value: str) -> None:
        """Bold label followed by normal text (11 pt)."""
        p = self.d.add_paragraph()
        self._run(p, label, 11, bold=True)
        self._run(p, value, 11)

    def bullets(self, items: List[str]) -> None:
        """Bulleted list (11 pt)."""
        for item in items:
            p = self.d.add_paragraph(style="List Bullet")
            self._run(p, item, 11)

    def code(self, text: str, caption: str) -> None:
        """Monospace block with a small caption above it."""
        c = self.d.add_paragraph()
        c.paragraph_format.keep_with_next = True
        self._run(c, caption, 9.5, italic=True, color="555555")
        p = self.d.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear")
        shade.set(qn("w:fill"), "F2F2F2")
        p._p.get_or_add_pPr().append(shade)
        self._run(p, text, 8.5, mono=True)

    def table(self, rows: List[List[Any]], widths: Optional[List[float]] = None, header: bool = True, size: float = 9.5) -> None:
        """Table with small text and a bold header row."""
        t = self.d.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                cell = t.cell(i, j)
                cell.text = ""
                self._run(cell.paragraphs[0], str(value), size, bold=header and i == 0)
                cell.paragraphs[0].paragraph_format.space_after = Pt(2)
                if i < len(rows) - 1 and len(rows) <= 24:
                    cell.paragraphs[0].paragraph_format.keep_with_next = True
                if widths:
                    cell.width = Inches(widths[j])
            row_props = t.rows[i]._tr.get_or_add_trPr()
            row_props.append(OxmlElement("w:cantSplit"))
        self.d.add_paragraph()

    def figure(self, key: str, width: float = 6.2) -> None:
        """A screenshot (or an empty labelled slot) with its caption."""
        number = fig_no(key)
        PLACED.append(key)
        caption, how = FIGS[key]
        matches = [m for m in sorted(SHOTS.glob(f"{key}.*")) + sorted(SHOTS.glob(f"*_{key}.*")) if m.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if matches:
            self.d.add_picture(str(matches[0]), width=Inches(width))
            self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            self.d.paragraphs[-1].paragraph_format.keep_with_next = True
        else:
            t = self.d.add_table(rows=1, cols=1)
            t.style = "Table Grid"
            cell = t.cell(0, 0)
            cell.text = ""
            self._run(cell.paragraphs[0], f"[Paste screenshot for Figure {number} here]\n{how}", 10, color="888888", italic=True)
            for _ in range(5):
                cell.add_paragraph()
        cap = self.d.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._run(cap, f"Figure {number} - {caption}", 9.5, color="333333")

    def figs(self, *keys: str) -> None:
        """Several figures one below the other."""
        for k in keys:
            self.figure(k)

    def page_break(self) -> None:
        """Start a new page."""
        self.d.add_page_break()

    def save(self, path: Path) -> None:
        """Write the .docx."""
        self.d.save(path)


# ------------------------------------------------------------- data for tables
def part2_records() -> List[Dict[str, Any]]:
    """The three Part 2 evaluator records."""
    data = load("part2_eval.json") or {}
    return data.get("records", [])


def part2_rows() -> List[List[Any]]:
    """Table of the Part 2 questions and their scores."""
    rows: List[List[Any]] = [["Trace id", "Question", "Plan", "Draft", "Final", "Final - draft", "Reviewer"]]
    for r in part2_records():
        question = r["question"].split("\n")[0]
        rows.append([r["trace_id"][:8] + "…", short(question, 54), r["plan_quality"]["score"], r["writer_helpfulness"]["score"], r["final_helpfulness"]["score"], r["improvement"]["difference"], f"{r['reviewer']['status']} {r['reviewer']['score']}/10"])
    return rows


def validation() -> Dict[str, Any]:
    """part3_validation.json."""
    return load("part3_validation.json") or {}


def case_rows() -> List[List[Any]]:
    """Raw per-case data: human label, three judge runs, difference."""
    rows: List[List[Any]] = [["Case", "Question", "Human", "Judge 1", "Judge 2", "Judge 3", "|Human - Judge 1|"]]
    for c in validation().get("cases", []):
        rows.append([c["case_id"], short(c["question"], 56), c["human_score"], c["judge_run1"], c["judge_run2"], c["judge_run3"], c["abs_diff_run1"]])
    return rows


def stats_rows() -> List[List[Any]]:
    """Headline numbers of the validation."""
    v = validation()
    if not v:
        return [["Measure", "Value"], [PENDING, ""]]
    val, rep = v["validation"], v["repeatability"]
    return [
        ["Measure", "Value"],
        ["Cases scored (judge failures)", f"{val['n']} ({val['n_missing']})"],
        ["Spearman correlation, human vs judge (run 1)", f"{val['spearman']} (p = {val['p_value']})"],
        ["Mean absolute difference", f"{val['mad']} points on the 1-5 scale"],
        ["Mean bias (judge minus human)", f"{val['mean_bias']:+}"],
        ["Exact agreement / within one point", f"{val['exact_agreement_pct']}% / {val['within_one_pct']}%"],
        ["Repeatability: runs, scores that changed", f"{rep['runs']} runs, {rep['cases_changed']} of {rep['cases']} cases changed ({rep['fraction_changed'] * 100:.0f}%)"],
        ["Repeatability: mean and max absolute change", f"{rep['mean_abs_change']} and {rep['max_abs_change']}"],
    ]


def extra_validation() -> Dict[str, Any]:
    """Numbers I compute from the raw cases: label spread, bootstrap interval, flagging."""
    cases = validation().get("cases", [])
    human = np.array([c["human_score"] for c in cases], dtype=float)
    judge = np.array([c["judge_run1"] for c in cases], dtype=float)
    counts = {int(k): int((human == k).sum()) for k in sorted(set(human))}
    rng = np.random.default_rng(4833)
    boots = []
    for _ in range(5000):
        idx = rng.integers(0, len(cases), len(cases))
        if len(set(human[idx])) < 2 or len(set(judge[idx])) < 2:
            continue
        boots.append(float(spearmanr(human[idx], judge[idx])[0]))
    low, high = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (float("nan"), float("nan"))
    h_low = {c["case_id"] for c in cases if c["human_score"] <= 3}
    j_low = {c["case_id"] for c in cases if c["judge_run1"] <= 3}
    return {"counts": counts, "ci": (low, high), "human_low": sorted(h_low), "judge_low": sorted(j_low), "both": sorted(h_low & j_low)}


def latency_rows() -> List[List[Any]]:
    """The 4.3 table."""
    data = load("part4_latency.json")
    rows: List[List[Any]] = [["Stage", "p50 (ms)", "p95 (ms)", "% of cache-miss end-to-end"]]
    if not data:
        return rows + [[PENDING, "", "", ""]]
    for r in data["table"]["rows"]:
        rows.append([r["stage"], f"{r['p50_ms']:,.1f}", f"{r['p95_ms']:,.1f}", f"{r['share_pct']:.1f}"])
    return rows


def trace_rows() -> List[List[Any]]:
    """The three named traces."""
    data = (load("part4_traces.json") or {}).get("traces", {})
    rows: List[List[Any]] = [["Trace", "trace_id", "Question", "Result"]]
    if not data:
        return rows + [[PENDING, "", "", ""]]
    miss, hit, fail = data["cache_miss_success"], data["cache_hit"], data["failed"]
    rows += [
        ["Cache miss, success", miss["trace_id"], short(miss["question"], 60), "ok, full pipeline"],
        ["Cache hit", hit["trace_id"], short(hit["question"], 60), f"ok, similarity {hit['similarity']}"],
        ["Failed", fail["trace_id"], fail["question"], f"error at stage {fail['failing_stage']}: {fail['error']}"],
    ]
    return rows


def span_stats() -> Dict[str, Any]:
    """Numbers from the span log that the Summary page also shows."""
    from hw10 import tracing

    spans = tracing.read_spans(config.SPANS_PATH)
    return stats.summary_metrics(tracing.group_by_trace(spans))


# ------------------------------------------------------------------------ text
def build(canvas: bool, commit: str) -> Doc:
    """Write the whole report text."""
    PLACED.clear()
    d = Doc()
    lat = load("part4_latency.json") or {}
    table = (lat.get("table") or {})
    rows_by = {r["stage"]: r for r in table.get("rows", [])}
    summ = span_stats()
    val = validation()
    ex = extra_validation()
    records = dash_data.evaluation_records()

    d.title("DATA 260: Agentic AI")
    d.centered("Instructor: Prof. Dr. Simon Shim   |   Student Name: Trapti Kulshrestha   |   STUDENT ID: 019124833   |   Homework: 10")
    d.label("GitHub Repository: ", REPO_URL)

    d.h1("Section 0: Personal Configuration")
    d.table([
        ["Setting", "Value"],
        ["SID4", "4833"],
        ["PORT_BASE", "8333 (8000 + 4833 mod 900)"],
        ["PREFIX", "s4833 (every Redis key and index name starts with it)"],
        ["SEED", "4833"],
        ["VERIFY_SEED", "264833"],
        ["DOMAIN_ID", "1 (4833 mod 8)"],
        ["Assigned Domain", "Clinical Trial Listings"],
    ], [2.2, 4.4])  # fmt: skip
    d.label("Hardware: ", "Apple MacBook Pro")
    d.label("Local Model: ", "qwen3:8b (Ollama), seed 4833, temperature 0 for the judge. No hosted API is used anywhere.")
    d.label("Embedding model: ", "nomic-embed-text (Ollama), 768 dimensions")
    d.label("Evaluation library: ", "DeepEval 4.3.4 (GEval) with a local judge; Streamlit 1.67.0 for the dashboard")
    d.label("Messaging and cache: ", "Kafka (HW8 topics and agents), Redis Stack (semantic cache)")
    if canvas:
        d.label("Tagged commit (tag hw10): ", commit)

    d.h1("Project Setup")
    d.p(
        "HW10 sits on top of HW8 (the Kafka Planner, Writer and Reviewer) and HW9 (the semantic cache), in the same repository. The new code is in the hw10/ package and a few top-level scripts, so the earlier homework is untouched, with three small additions I should name: new targets at the end of the Makefile, two new lines in requirements.txt (deepeval and streamlit) and a few lines in .gitignore for generated HW10 files. Nothing from HW2 to HW9 was edited."
    )
    d.p(
        "The Kafka topics are the HW8 topics, unchanged (s4833_inbox, s4833_tasks, s4833_drafts, s4833_final and s4833_dead_letter). The three agents run in three terminals, one process each, and they are the same Planner, Writer and Reviewer logic as in HW8 with a thin wrapper that writes a span for every attempt. "
        + f"{ref('agent_planner', 'agent_writer', 'agent_reviewer')} show them running, and {ref('tests')} shows the 11 offline tests passing."
    )
    d.figs("agent_planner", "agent_writer", "agent_reviewer", "tests")
    d.p(
        "One design choice needs saying here because it shows up in the numbers. HW9's cache was reusable as it was, but its index already holds many near-identical trial-code questions (for example CT-2026-10x), and nomic-embed-text scores such questions as more than 0.85 similar. A fresh test question was therefore answered from the old cache instead of going through the pipeline, which would have made my cache-miss measurements invalid. HW10 uses its own cache namespace (keys s4833:hw10:semcache:, index s4833:idx:hw10cache), with the same 0.85 threshold, so every cache-miss request in this report really reached the Kafka pipeline. Three stray HW10 entries from my first test runs remain in the HW9 namespace; they are harmless."
    )
    d.table([
        ["Step", "Command"],
        ["Start Kafka and Redis", "make up-hw08 ; make up-hw09"],
        ["Agents (three terminals)", "python hw10_agents.py planner | writer | reviewer"],
        ["Part 1 dashboard", "streamlit run hw10_dashboard.py"],
        ["Part 2 evaluator", "python run_hw10_part2.py"],
        ["Part 3 judge validation", "python make_hw10_cases.py ; python label_hw10_cases.py ; (commit the two files) ; python run_hw10_part3.py all"],
        ["Part 4 tracing", "python run_hw10_part4.py traces ; python run_hw10_part4.py latency --n 50 ; python run_hw10_part4.py hits --n 20"],
        ["Self-check", "make verify-hw10"],
    ], [1.9, 4.7])

    # ------------------------------------------------------------------ Part 1
    d.h1("Part 1 - Streamlit Dashboard")
    d.p(
        "The dashboard is one Streamlit app (hw10_dashboard.py) with three pages in the sidebar: Summary, Evaluation and Trace lookup. It reads only files that my runs wrote (the span log and the result files in reports/hw10/raw/), so it shows real data and needs no running agents. Every number on a page has a line under it that states its time window and its data source, which is how the assignment asks for it. On the Summary page the time window can be changed in the sidebar (15 minutes, 1 hour, 24 hours, 7 days or all logged requests); the screenshots use all logged requests, because my runs were spread over the day."
    )
    d.h2("1.1 Summary page")
    d.p(
        "The page shows the number of recent requests, the cache hit rate with the hits and the misses as separate numbers, the error rate and the end-to-end latency. Hits and misses are kept in separate latency populations everywhere, since a hit takes milliseconds and a miss takes seconds and an average of the two would describe neither."
    )
    d.table([
        ["Metric", "Value in the screenshots", "Window", "Data source"],
        ["Requests", f"{summ['requests']}", "all logged requests", "one request span per request"],
        ["Cache hit rate", f"{summ['hit_rate_pct']}% ({summ['hits']} hits, {summ['misses']} misses)", "all logged requests", "cache_lookup spans (similarity at or above 0.85)"],
        ["Error rate", f"{summ['error_rate_pct']}% ({summ['errors']} failed request)", "all logged requests", "status of the request span"],
        ["p95 end-to-end latency", f"{summ['latency_all']['p95']:,.0f} ms", "all logged requests", "request span: start of request to answer returned; evaluation not included"],
        ["Cache-hit latency p50 / p95", f"{summ['latency_hit']['p50']} / {summ['latency_hit']['p95']} ms", "all logged requests", "request spans of hits only"],
        ["Cache-miss latency p50 / p95", f"{summ['latency_miss']['p50']:,.1f} / {summ['latency_miss']['p95']:,.1f} ms", "all logged requests", "request spans of misses only"],
    ], [1.5, 1.8, 1.1, 2.3])
    d.p(
        "The hit rate of 30.4% is not a measurement of how a real service would behave. The log contains my deliberate runs: 20 questions asked a second time to measure hit latency, 55 misses and one injected failure. I show the number because the page calculates it correctly, not because it says anything about real traffic. The one failed request (1.3%) is the failed trace from Part 4, which I created on purpose."
    )
    d.figs("dash_summary_top", "dash_summary_charts")
    d.p(
        "The page also has a bar chart of hits and misses, a table of where a cache miss spends its time (the same table as Part 4.3), a chart of request latency over time (logarithmic, so hits and misses both show) and a list of recent requests with their trace ids, which can be pasted into the Trace lookup page."
    )
    d.h2("1.2 Evaluation page")
    d.p(
        "The Evaluation page has two parts. The first part shows the Part 2 scores by pipeline stage (Planner plan quality, Writer draft helpfulness, Reviewer final-answer helpfulness) as a bar chart and as a table with one row per evaluated trace. The judge's reasons are available from the stored results. The page covers the 3 questions of Part 2 and the 50 cache-miss requests of Part 4.3, so 53 evaluated traces. Below that is a short interpretation of how the Planner, the Writer and the Reviewer worked together. The second part shows the Part 3 judge validation: Spearman correlation, mean absolute difference, the share of scores that changed between runs and the largest change, the raw per-case table and a grid of human labels against judge scores."
    )
    d.figs("dash_eval_top", "dash_eval_bottom")
    d.h2("1.3 Trace lookup page")
    d.p(
        "The Trace lookup page takes a trace_id and shows the whole journey of that request in stage order, with the start, end, duration, status and error of every stage, followed by a timeline chart. A cache hit and a cache miss are told apart in plain words above the table: a hit says that it was answered from the semantic cache and that the Kafka pipeline was not used, and its only spans are the cache lookup and the request. A miss lists the cache lookup, the queue waits and the Planner, Writer and Reviewer. A failed request additionally shows the failing stage and its error in a highlighted box. The three traces are in Part 4 ("
        + ref("trace_miss", "trace_hit", "trace_failed")
        + ")."
    )
    d.h2("1.4 What is cached and why")
    d.p(
        "I used both Streamlit caching decorators, for two different jobs. @st.cache_resource is for an object that must exist once for the whole server and must not be copied: a small SpanSource object that knows where the span file and the result folder are. @st.cache_data is for results computed from data: the parsed span file and the result JSON files. Streamlit stores a copy of those per set of arguments, which is right for data. The modification time of the file is one of the arguments, so a file that my run has changed is loaded again, and the cache entries expire after 10 seconds, so a measurement that is still running shows up on the page without a restart. The statistics themselves (percentiles and so on) are cheap and are computed on every run of a page."
    )
    d.p("The code that does this is in "+ref("code_common")+".")
    d.figure("code_common")

    # ------------------------------------------------------------------ Part 2
    d.h1("Part 2 - Evaluator for the Planner, Writer and Reviewer Pipeline")
    d.h2("2.1 Joining the pipeline messages")
    d.p(
        "A request goes through the HW8 topics as the Planner's plan (s4833_tasks), the Writer's draft (s4833_drafts) and the Reviewer's final message (s4833_final). All three carry the same correlation_id, which is the trace_id of HW10. A collector (hw10/collector.py) consumes those topics plus the dead-letter topic, keeps the original messages untouched and joins plan, draft and final by correlation_id. The joined bundle of each request, with the three original messages inside, is saved in reports/hw10/raw/joined/<trace_id>.json, so a score can always be traced back to the exact messages that were judged."
    )
    d.h2("2.2 The four criteria and the judge")
    d.table([
        ["Criterion", "What it looks at", "What is reported"],
        ["Plan Quality", "The Planner's steps for the question: relevant, specific, in a sensible order, nothing invented", "score 1-5 and the judge's reason"],
        ["Writer Helpfulness", "The Writer's draft for the question", "score 1-5, the reason and the trace_id"],
        ["Final Answer Helpfulness", "The final answer the user receives", "score 1-5, the reason and the final answer text"],
        ["Final-vs-Draft Improvement", "Both scores side by side", "draft score, final score, difference and a one-line interpretation"],
    ], [1.6, 3.2, 1.8])
    d.p(
        "The judge is DeepEval's GEval metric with qwen3:8b through Ollama as a custom DeepEvalBaseLLM class (OllamaJudge in hw10/judge.py): temperature 0, seed 4833, and the answer is forced to a JSON schema. There is no hosted model. All scores are on a 1 to 5 scale, the same scale as my human labels. GEval works on 0 to 10 internally, so the rubric has five bands (0-2 gives 1, 3-4 gives 2, 5-6 gives 3, 7-8 gives 4, 9-10 gives 5), and I store both numbers. Every call is bounded: the HTTP request to Ollama has a 5 second connect and a 90 second read timeout, and each metric runs in a worker thread that is abandoned after 240 seconds. A judge that is down, slow or answers with broken JSON gives a score of None with a status (timeout, judge_error, bad_judge_output or invalid_input) and an error message, instead of hanging the evaluator or crashing it. A missing plan, draft or final message gives invalid_input in the same way, which is what the failed trace in Part 4 shows."
    )
    d.p("The bounded judge call is in "+ref("code_score_text")+".")
    d.figure("code_score_text")
    d.h2("2.3 End-to-end examples")
    d.p(
        "I sent three questions through the live pipeline and evaluated each one after it finished: a listing lookup with facts from the database, a general question and a category lookup. "
        + f"{ref('part2_run')} shows the run. The scores are in the table and the full reasons are on the Evaluation page."
    )
    d.figs("part2_run")
    d.table(part2_rows(), [0.7, 2.3, 0.45, 0.45, 0.45, 0.7, 1.0], size=9)
    recs = part2_records()
    if recs:
        r = recs[0]
        d.p(
            f"Take the first question as a worked example (trace {r['trace_id']}). The Planner produced three steps: \"{r['plan_quality']['plan'][0]}\" \"{r['plan_quality']['plan'][1]}\" \"{r['plan_quality']['plan'][2]}\" The judge gave the plan {r['plan_quality']['score']}/5 (its reason is on the Evaluation page). The Writer's draft was \"{r['writer_helpfulness']['draft']}\" and got {r['writer_helpfulness']['score']}/5. The Reviewer approved it with {r['reviewer']['score']}/10, and the final answer got {r['final_helpfulness']['score']}/5."
        )
    d.h2("2.4 The final answer did not improve on the draft")
    d.p(
        "The Final-vs-Draft criterion has to be reported honestly: in all three questions the final answer scored exactly the same as the draft (difference 0), and so it did in all 53 evaluated traces, including the 50 cache-miss requests of Part 4. The reason is how the HW8 Reviewer works. It scores the draft and either approves it or sends it back, and when it approves, the final message contains the draft word for word. The evaluator checks this by comparing the two texts, and they were identical in 53 of 53 traces, with no draft rejected. So an improvement from the Reviewer is impossible by design in this system, and a difference of 0 does not mean the Reviewer is bad. It means that the Reviewer is a gate and not an editor. I did not change the HW8 Reviewer to make the number look better. Making the Reviewer rewrite weak drafts would be the way to make an improvement measurable, and that is future work."
    )
    d.p(
        "Across the 53 scored traces the mean plan quality was "
        + f"{np.mean([r['plan_quality']['score'] for r in records]):.2f}, the mean draft helpfulness {np.mean([r['writer_helpfulness']['score'] for r in records]):.2f} and the mean final helpfulness {np.mean([r['final_helpfulness']['score'] for r in records]):.2f}. "
        "Plan quality and draft helpfulness have a Spearman correlation of only 0.12, so a good-looking plan told me very little about whether the draft would be good: the Writer (qwen3:8b with the listing facts in the prompt) mostly produced a good answer whatever the plan looked like. The Reviewer approved every draft, with scores of 9 or 10 out of 10. That fits the judge's scores, since 39 of 53 drafts got a 5, but it also means that neither the Reviewer nor the judge separated the drafts well. The Planner was the stage with the lowest and most varied score (nine plans were rated 3)."
    )

    # ------------------------------------------------------------------ Part 3
    d.h1("Part 3 - Judge Validation")
    d.h2("3.1 The 20 drafts and my labels")
    d.p(
        "make_hw10_cases.py asks the same Planner and Writer roles as before (qwen3:8b, temperature 0, seed 4833) for 20 drafts and saves them in data/hw10/eval_cases.json. The questions are a deliberate mix so that the drafts do not all look alike: six listing lookups with database facts (one about a trial that does not exist), general questions about clinical trials, a comparison, and a few vague, unanswerable or off-topic requests (for example the weather in San Jose and a poem). No score of any kind is stored in the file. "
        + f"{ref('cases_made')} shows the run."
    )
    d.figs("cases_made")
    c = ex["counts"]
    d.p(
        "I then labeled the 20 drafts by hand with label_hw10_cases.py, which shows one draft at a time with its question and facts and asks for a number from 1 to 5, using a short guide with the same five descriptions as the judge's rubric (5 fully helpful and correct, down to 1 unhelpful, wrong, off-topic or empty). The labels are mine. No model produced or suggested them, and I never changed one after saving it. My labels are "
        + ", ".join(f"{n} labels of {k}" for k, n in sorted(c.items(), reverse=True))
        + ". That spread matters later: most of my labels are 5."
    )
    d.figs("label_prompt", "label_commit")
    d.p(
        "I committed eval_cases.json and human_labels.csv together in commit 0befa57f63084d711fd846d198ab56969c577cac (two files, 270 insertions) before the judge had scored a single draft. run_hw10_part3.py refuses to run unless both files are committed and unchanged, and it prints that commit on every run, which you can see in the screenshots below."
    )
    d.h2("3.2 Running the judge and the results")
    d.p(
        "The judge ran on all 20 drafts three times with the same inputs and the same settings (model, temperature 0, seed 4833, same rubric). Every one of the 20 cases got a valid score in run 1 (no judge failures), and runs 2 and 3 matched it. "
        + f"{ref('part3_start', 'part3_end')} show the three runs and the statistics block."
    )
    d.figs("part3_start", "part3_end")
    d.table(stats_rows(), [3.4, 3.2])
    d.p(
        f"The bootstrap 95% interval for the Spearman correlation (resampling the 20 cases, seed 4833) is about {ex['ci'][0]:.2f} to {ex['ci'][1]:.2f}, so with only 20 cases I cannot say much more than that the agreement is weak to moderate. The raw per-case data are below, with the judge's three runs side by side; the judge's reason for each case is in part3_per_case.csv and on the Evaluation page."
    )
    d.table(case_rows(), [0.45, 3.0, 0.55, 0.6, 0.6, 0.6, 0.85], size=8.5)
    d.h2("3.3 Reading the results")
    d.p(
        "The headline numbers look moderate: a mean absolute difference of 0.5 points, exact agreement on 65% of the cases and agreement within one point on 90%. The table underneath shows why they are less comforting than they look. Seven of the 20 judge scores differ from mine. In five of those seven the judge is higher than I am (the other two, C16 and C19, are lower), and four times (C07, C09, C12, C13) it gave a 5 to a draft that I scored 3 or 4. So on borderline drafts the judge is more generous than I am, and it rarely marks anything down. The mean bias of +0.1 hides this because the one big disagreement in the other direction cancels part of it."
    )
    d.p(
        "That big disagreement is case C19, the poem about clinical trials. I labeled it 5 and the judge gave it 2 in all three runs. The judge's reason says the poem does not address a clinical trial listings service. My label of 5 treats the poem as a good answer to what the user asked. This is a disagreement about what 'helpful' means for an off-topic request, not random noise, and my rubric text for the judge (which mentions a listings service) pushed it that way. I did not change the label or the rubric afterwards. The other off-topic case, C18 (the weather), is one where both of us scored 2, because the draft claims to have checked a weather source and invents a forecast."
    )
    d.p(
        f"The overall Spearman of {val['validation']['spearman']} has a p-value of {val['validation']['p_value']}, which is not significant at the usual 0.05 level, and 13 of my 20 labels are 5, so there are many ties and little range to correlate over. If I treat a score of 3 or lower as 'this draft needs fixing', I flagged {len(ex['human_low'])} drafts ({', '.join(ex['human_low'])}) and the judge flagged {len(ex['judge_low'])} ({', '.join(ex['judge_low'])}). They agree only on {', '.join(ex['both']) or 'none'}, so the judge's precision for finding bad drafts was 1 of 2 and its recall 1 of 3. That is the number I would care about most for a quality gate, and it is poor."
    )
    d.h2("3.4 Repeatability")
    d.p(
        "Across the three runs, 0 of 20 scores changed: the fraction of changed scores is 0%, the mean absolute change is 0.0 and the maximum change is 0. With temperature 0, a fixed seed, the same model and the same prompt on the same machine, that is what I expected, and it is a good property: a score does not wander from run to run. It is also a narrow result. It shows that this exact setup is deterministic, not that the judge would give the same score after a paraphrase of the rubric, a different model version, different hardware or a draft that is slightly reworded. I compared the scores only, not the wording of the reasons."
    )
    d.h2("3.5 Would I trust this judge to gate a deployment?")
    d.p(
        "No, not on its own. It is perfectly repeatable, but repeatable is not the same as right. On my 20 drafts it agrees with me on 65% of the cases and its correlation with my labels is weak (0.36, not significant, and a wide interval). It is too generous on borderline drafts, so a gate built on it would let mediocre answers through, and it finds only one of my three weak drafts. It also scored a draft I considered fully helpful as 2 because of a rubric wording choice, so it would block some good answers too. It could still be useful as a cheap first filter that catches obvious failures such as the invented weather forecast, with a human looking at everything else."
    )
    d.p("The extra evidence I would need before letting it gate anything:")
    d.bullets(
        [
            "Many more labeled cases (a few hundred), with a balanced spread of scores. My 20 labels are mostly 5s, so the judge was barely tested on bad drafts.",
            "A second human labeler on the same drafts, to measure how much two humans agree with each other. A judge cannot be expected to agree with me more than another person would.",
            "A pass or fail view, not only a correlation: precision and recall for catching the drafts that should be blocked, with a threshold chosen on one part of the data and tested on another.",
            "Robustness checks: a different seed, a reworded rubric, a second model version, different hardware, and reworded or longer drafts, to see whether the scores stay put.",
            "Drafts taken from real pipeline traffic, not questions I wrote to test the judge, and a check of whether the judge favours longer or more confident answers.",
            "A clear rule for off-topic requests, written down before labeling, so that the judge and the human are asked the same question.",
        ]
    )

    # ------------------------------------------------------------------ Part 4
    d.h1("Part 4 - Tracing and Latency")
    d.h2("4.1 How the tracing works")
    d.p(
        "The HW8 correlation_id is the trace_id. The ingress creates it, writes it into the question message on the inbox topic, and from there it is carried by the Planner's plan, the Writer's draft and the Reviewer's final message, and by the evaluator, which joins the messages by it. No new id exists. Each stage writes one JSON span {trace_id, stage, start, end, status, error} (plus duration_ms, a component name and a few attributes such as the partition and offset) as one line into reports/hw10/raw/spans.jsonl. The stages are cache_lookup, queue_inbox, planner, queue_tasks, writer, queue_drafts, reviewer, queue_final, dead_letter, request and evaluation."
    )
    d.p(
        "A queue-wait span runs from the Kafka record's own timestamp, the moment the message was put on the topic, to the moment the next agent picks it up, so it measures waiting in Kafka and not work. The request span is the time the user waits: from the start of the request to the answer returned, and it does not include the evaluation, which runs after the answer is back. Each handler attempt writes its own span, so a retried Writer shows up as several spans, and a message that is given up on after three attempts also gets a dead_letter span with the error."
    )
    d.p("The two functions that create and write a span are in "+ref("code_tracing")+", and the wrapper that every agent uses is in "+ref("code_traced")+".")
    d.figs("code_tracing", "code_traced")
    d.h2("4.2 One cache-hit, one cache-miss and one failed trace")
    d.p(
        "run_hw10_part4.py traces made the three traces, saved their ids in part4_traces.json, and the dashboard reads the same file. "
        + f"{ref('part4_traces')} is the terminal output and the table gives the ids. The Trace lookup page shows each of them ({ref('trace_miss', 'trace_hit', 'trace_failed')})."
    )
    d.table(trace_rows(), [1.1, 2.4, 1.8, 1.4], size=8.5)
    d.figs("part4_traces", "trace_miss")
    d.p(
        "The cache-miss trace asked for the participant capacity and category of trial CT-2026-103. It went through cache_lookup (a miss), queue_inbox, planner (2054 ms), queue_tasks, writer (2374 ms), queue_drafts, reviewer (1579 ms, approved 10/10) and queue_final. The request returned the answer after 6067 ms, and the evaluation stage then took another 10358 ms. The queue waits were small."
    )
    d.figs("trace_hit")
    d.p(
        "The cache-hit trace is the same question asked again. Its only spans are cache_lookup (hit, similarity 1.0) and request, both about 60 ms, and there is no Planner, Writer, Reviewer or Kafka message. This one request took 60.9 ms, longer than the typical hit (the 24 hits in the log have a p50 of 16.5 ms), and I did not investigate why; I note it because it is the figure that is on the screenshot."
    )
    d.figs("trace_failed")
    d.p(
        "The failed trace was made on purpose, with fault injection: the inbox message carries inject_fault = bad_plan, and the traced Planner then publishes an empty plan. The Writer rejects it with ValueError: plan must be a non-empty list of non-empty strings, on all three attempts (the HW8 retry rule), and the message is dead-lettered. The failing stage is therefore the writer, even though the cause was put in at the Planner. The request span ends with status error after 3063 ms, there is a dead_letter span with the same error, and the evaluation span is an error too, because there is no plan, draft or final message to judge. This is a deliberate failure, not one that happened by chance."
    )
    d.h2("4.3 Latency of 50 confirmed cache-miss requests")
    d.p(
        "I sent 50 distinct questions (from a pool of 70 in data/hw10/latency_questions.json) one at a time. For each request the script checks the cache_lookup span: a request only counts if it was a miss (similarity below the threshold of 0.85) and if it then went through the whole Planner, Writer and Reviewer path. One question was answered by the cache with a similarity of 0.862, so it was skipped and replaced by the next question in the pool; it is not in the 50. The highest similarity among the 50 counted requests was 0.8385, all 50 ran the full pipeline and all 50 were approved by the Reviewer. "
        + f"{ref('part4_latency')} is the run."
    )
    d.figs("part4_latency")
    d.p(
        "End-to-end in this table means everything a cache miss costs: cache lookup, the queue waits, Planner, Writer, Reviewer and the evaluation. The percentage is the share of the summed time over all 50 requests (the sum of one stage divided by the sum of all stages), so a few short requests cannot distort it. The p50 and p95 values are per request, so the p50 of the parts does not add up to the p50 of the total."
    )
    d.table(latency_rows(), [2.4, 1.2, 1.2, 1.8])
    ev = rows_by.get("Evaluation", {})
    wr = rows_by.get("Writer", {})
    d.p(
        f"The dominant contributor is the evaluation stage: {ev.get('share_pct')}% of the cache-miss end-to-end time (p50 {ev.get('p50_ms'):,.0f} ms, p95 {ev.get('p95_ms'):,.0f} ms). It is the judge making four calls to qwen3:8b for every request. The Writer is next with {wr.get('share_pct')}% (p50 {wr.get('p50_ms'):,.0f} ms). The Planner and the Reviewer each take about 10%, and the cache lookup (p50 {rows_by['Cache lookup']['p50_ms']} ms) and the Kafka queue waits (p50 {rows_by['Queue wait (total)']['p50_ms']} ms, together under 1%) are negligible. Kafka is not what makes a request slow here, and for the three model stages the p95 is within about 40% of the p50."
    )
    d.p(
        f"The user does not wait for the evaluation, though. The latency of the request span, which stops when the answer is returned, was p50 {table.get('user_facing_p50_ms'):,.1f} ms and p95 {table.get('user_facing_p95_ms'):,.1f} ms. Of what the user actually waits for, the Writer is by far the largest part: 21.8 of the 41.6 percentage points that are not evaluation, about half."
    )
    d.p(
        "What I would optimize first depends on what is being optimized. For the cost and load of the pipeline, the evaluation, because it is the biggest block and its work is not needed for the answer: I would run it asynchronously and not in sequence with the request, evaluate only a sample (say one request in five) instead of all of them, and use fewer criteria or a smaller judge for routine checks. That does not make a user's answer faster. For the time a user waits, the first target is the Writer, for example by limiting the length of the generated text, since it is about half of the user-facing time and the Planner's and the Reviewer's calls would be next. The cache is already the biggest win, as the next paragraph shows."
    )
    d.h2("Cache-hit latency (kept separate)")
    d.p(
        "Cache-hit latency is not part of the table above. I asked 20 questions a second time, and all 20 were cache hits, in 14 to 32 ms each "
        + f"({ref('part4_hits')}). On the dashboard the hit latency has its own tile and its own row, with a p50 of {summ['latency_hit']['p50']} ms and a p95 of {summ['latency_hit']['p95']} ms over all {summ['hits']} hits in the log, against a cache-miss p50 of {summ['latency_miss']['p50']:,.0f} ms, about {summ['latency_miss']['p50'] / summ['latency_hit']['p50']:.0f} times slower. The cache-lookup stage of a miss (p50 {rows_by['Cache lookup']['p50_ms']} ms) is slower than a whole hit request in this log, and I did not look into why, so I would not use the two numbers to say what a lookup alone costs."
    )
    d.figs("part4_hits")

    # ------------------------------------------------------------------ Self-check
    d.h1("Self-check")
    d.p(
        "make verify-hw10 runs verify_hw10.py. It checks that Kafka, Redis and Ollama are reachable and the agents are available, that the local judge answers within its time limit, that the 11 offline tests pass, that eval_cases.json and human_labels.csv were committed before the judge ran and are unchanged (and that all three judge runs used that commit), that the Part 2 records have all four criteria, that the Part 3 statistics exist, that the three named traces have the expected path and status, that there are 50 confirmed cache-miss requests that all ran the full pipeline, and that the dashboard script runs on the real logs. It writes reports/hw10/verification.json. "
        + f"{ref('verify')} shows the run ending with OVERALL: PASS."
    )
    d.figs("verify")
    d.h2("Limitations")
    d.bullets(
        [
            "The Reviewer never edits, so the Final-vs-Draft criterion is always 0 here; the criterion works but this pipeline cannot show an improvement.",
            "The judge was validated on 20 drafts, and 13 of my labels are 5. The correlation is weak and not significant, and the judge is lenient on borderline drafts.",
            "Repeatability was measured with fixed settings on one machine and says nothing about other conditions.",
            "The failed trace is an injected fault, not a naturally occurring one. The 30.4% cache hit rate on the dashboard comes from my deliberate runs.",
            "The 50-request latency run asked one question at a time. It says nothing about behaviour under load, where queue waits would grow.",
            "All timings are from one MacBook with one local model, so they describe this setup and not a production system.",
        ]
    )

    d.h1("AI Use")
    ai = (OUT / "AI_USE.md").read_text(encoding="utf-8") if (OUT / "AI_USE.md").exists() else ""
    for block in ai.split("\n## ")[1:]:
        heading, _, body = block.partition("\n")
        d.h2(heading.strip())
        for para in body.split("\n\n"):
            para = para.strip()
            if para and not para.startswith("<!--"):
                d.p(para.replace("`", ""))

    assert PLACED == ORDER, f"figure order mismatch: {PLACED}"
    return d


def to_pdf(docx_path: Path) -> Optional[Path]:
    """Convert with LibreOffice if it is installed."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("LibreOffice not found: open the .docx in Word and export to PDF.")
        return None
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(docx_path.parent), str(docx_path)], check=True, capture_output=True)
    return docx_path.with_suffix(".pdf")


def main() -> None:
    """Build the Git copy, and the Canvas copy when --commit is given."""
    parser = argparse.ArgumentParser(description="Build the HW10 report")
    parser.add_argument("--commit", default="", help="hw10 tag commit hash (Canvas copy)")
    parser.add_argument("--list-screenshots", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()
    if args.list_screenshots:
        for number, key in enumerate(ORDER, 1):
            have = bool(list(SHOTS.glob(f"{key}.*")) + list(SHOTS.glob(f"*_{key}.*")))
            caption, how = FIGS[key]
            print(f"{'[x]' if have else '[ ]'} {number:02d} {key}.png  {caption}\n        {how}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(False, "", "Report_editable.docx", "Report.pdf")]
    if args.commit:
        jobs.append((True, args.commit, "Kulshrestha_HW10_editable.docx", "Kulshrestha_HW10.pdf"))
    for canvas, commit, docx_name, pdf_name in jobs:
        path = OUT / docx_name
        build(canvas, commit).save(path)
        print(f"wrote {path}")
        if not args.no_pdf:
            made = to_pdf(path)
            if made and made.name != pdf_name:
                made.replace(OUT / pdf_name)
            if made:
                print(f"wrote {OUT / pdf_name}")


if __name__ == "__main__":
    main()
