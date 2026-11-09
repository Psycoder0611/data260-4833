# ruff: noqa: E501
"""Build the HW9 report (Word + PDF) from the raw files of my runs.

  python build_hw09_report.py                  Git copy: Report_editable.docx + Report.pdf
  python build_hw09_report.py --commit <hash>  also the Canvas copy:
                                               Kulshrestha_HW9_editable.docx + Kulshrestha_HW9.pdf
                                               (adds the tag hw9 and the commit hash)
  python build_hw09_report.py --list-screenshots

The text is written by me. Numbers in the tables are read from reports/hw09/raw/
(part1_counter.json, part2_results.json, part3_*.json, part4_*.json) and from
data/hw09/lessons.json. Anything not run yet shows "[run pending]".
Screenshots go in reports/hw09/screenshots/ as NN_key.png (see --list-screenshots).
A missing screenshot becomes an empty labelled slot, so I can also paste the
picture into the Word file by hand and export the PDF myself.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from hw9 import config

ROOT = Path(__file__).resolve().parent
OUT = config.REPORT_DIR
RAW = config.RAW_DIR
SHOTS = OUT / "screenshots"
REPO_URL = "https://github.com/Psycoder0611/data260-4833"
PENDING = "[run pending]"
FONT = "Calibri"

# key -> (caption, how to capture it). Order in the report = ORDER below.
FIGS = {
    # Part 1
    "code_counter": ("Code: increment_clinical_trial_views (hw9/cache_db.py)", "Editor screenshot of increment_clinical_trial_views()."),
    "counter_a": ("Part 1 output: Access #1 to #11, first sync to the database", "Terminal: `python demo_hw09_part1.py` (name visible), top part."),
    "counter_b": ("Part 1 output: Access #12 to #25 and the final check", "Same run, bottom part with 'Redis counter: 25 | database view_count: 20'."),
    "counter_db": ("Redis value and the database row after the run", "Terminal: `docker exec s4833-redis redis-cli get s4833:views:clinical_trial:1` and a SELECT of view_count for CT-2026-101."),
    # Part 2
    "code_cache": ("Code: lookup and store of the semantic cache (hw9/semantic_cache.py)", "Editor screenshot of SemanticCache.lookup() (and ensure_index())."),
    "code_qa": ("Code: QAService.answer, the cache at the ingress (hw9/qa_service.py)", "Editor screenshot of QAService.answer()."),
    "index_info": ("Redis vector index s4833:idx:semcache (FT.INFO)", "Terminal: `docker exec s4833-redis redis-cli FT.INFO s4833:idx:semcache` (the attributes part showing the VECTOR field)."),
    "part2_a": ("Part 2 run: queries 1 to 6 with HIT / MISS lines", "Terminal: `python run_hw09_part2.py`, first half."),
    "part2_b": ("Part 2 run: queries 7 to 12 and the summary", "Same run, second half with the Summary block."),
    # Part 3
    "cases_yaml": ("cache_cases.yaml (seed queries and the first cases)", "Editor screenshot of the top of cache_cases.yaml."),
    "sweep": ("Threshold sweep output (40 cases, five thresholds)", "Terminal: `python run_hw09_part3.py sweep` (the table at the end)."),
    "false_hit": ("One false hit in full", "Terminal: `python run_hw09_part3.py falsehit`."),
    "code_stale": ("Code: data-version check on a cache hit (hw9/qa_service.py, hw9/facts.py)", "Editor screenshot of the `if self.check_version` block and facts.current_version()."),
    "stale_a": ("Stale answer: UPDATE, then the old answer is served", "Terminal: `python run_hw09_part3.py stale`, steps [1] to [3]."),
    "stale_b": ("Invalidation with the data-version marker", "Same run, step [4] and the 'Restored' line."),
    # Part 4
    "code_answering": ("Code: Answering Agent (hw9/improve/agents.py)", "Editor screenshot of AnsweringAgent (load_lessons and answer)."),
    "code_evaluator": ("Code: Evaluator Agent and the reference check (hw9/improve/agents.py, reference.py)", "Editor screenshot of EvaluatorAgent.evaluate/propose_lessons and check_answer()."),
    "ref_data": ("reference_data.json (ground truth for the evaluator)", "Editor screenshot of the top of data/hw09/reference_data.json."),
    "revision": ("Complete revision sequence (controlled case)", "Terminal: `python run_hw09_part4.py demo-revision` (the summary block)."),
    "train": ("Training run: failures and the lessons created from them", "Terminal: `python run_hw09_part4.py train`."),
    "validate": ("Validation: each lesson kept or rejected", "Terminal: `python run_hw09_part4.py validate` (the Candidate lines and 'Kept lessons')."),
    "lessons_json": ("lessons.json after validation", "Editor screenshot of data/hw09/lessons.json."),
    "reuse": ("A stored lesson loaded for a later related question", "Terminal: `python run_hw09_part4.py demo-reuse`."),
    "final": ("Final test, four variants", "Terminal: `python run_hw09_part4.py final` (the table at the end)."),
    # self-check
    "verify": ("make verify-hw09: all checks pass", "Terminal: `make verify-hw09` (last lines with OVERALL: PASS)."),
}  # fmt: skip

ORDER = [
    "code_counter", "counter_a", "counter_b", "counter_db",
    "code_cache", "code_qa", "index_info", "part2_a", "part2_b",
    "cases_yaml", "sweep", "false_hit", "stale_a", "code_stale", "stale_b",
    "code_answering", "code_evaluator", "ref_data", "revision", "train",
    "lessons_json", "reuse", "validate", "final",
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

    def _run(
        self,
        p,
        text: str,
        size: float,
        bold: bool = False,
        mono: bool = False,
        color: Optional[str] = None,
        italic: bool = False,
    ):
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

    def table(
        self,
        rows: List[List[Any]],
        widths: Optional[List[float]] = None,
        header: bool = True,
    ) -> None:
        """Table with 9.5 pt text and a bold header row."""
        t = self.d.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                cell = t.cell(i, j)
                cell.text = ""
                self._run(cell.paragraphs[0], str(value), 9.5, bold=header and i == 0)
                cell.paragraphs[0].paragraph_format.space_after = Pt(2)
                # keep the whole table on one page: every row but the last
                # stays with the next row
                if i < len(rows) - 1:
                    cell.paragraphs[0].paragraph_format.keep_with_next = True
                if widths:
                    cell.width = Inches(widths[j])
            row_props = t.rows[i]._tr.get_or_add_trPr()
            row_props.append(OxmlElement("w:cantSplit"))
        self.d.add_paragraph()

    def figure(self, key: str) -> None:
        """A screenshot (or an empty labelled slot) with its caption."""
        number = fig_no(key)
        PLACED.append(key)
        caption, how = FIGS[key]
        matches = sorted(SHOTS.glob(f"{key}.*")) + sorted(SHOTS.glob(f"*_{key}.*"))
        matches = [m for m in matches if m.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if matches:
            self.d.add_picture(str(matches[0]), width=Inches(6.2))
            self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            self.d.paragraphs[-1].paragraph_format.keep_with_next = True
        else:
            t = self.d.add_table(rows=1, cols=1)
            t.style = "Table Grid"
            cell = t.cell(0, 0)
            cell.text = ""
            self._run(
                cell.paragraphs[0],
                f"[Paste screenshot for Figure {number} here]\n{how}",
                10,
                color="888888",
                italic=True,
            )
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
def part1_text() -> str:
    """One sentence about the Part 1 result, from the raw file."""
    d = load("part1_counter.json")
    if not d:
        return "[Part 1 not run yet.]"
    return (
        f"After {len(d['accesses'])} accesses the Redis counter was {d['redis_value']} "
        f"and the database column view_count was {d['database_view_count']}: the last "
        f"sync happened at access #{max(a['total'] for a in d['accesses'] if a['synced'])} "
        "and the five accesses after it are only in Redis until the next multiple of ten."
    )


def part2_rows() -> List[List[Any]]:
    """Table of the 12 Part 2 queries."""
    rows: List[List[Any]] = [["#", "Kind", "Query", "is_cached", "Similarity", "Latency (ms)"]]
    data = load("part2_results.json")
    if not data:
        return rows + [["", PENDING, "", "", "", ""]]
    for r in data["rows"]:
        rows.append([r["n"], r["kind"], short(r["query"], 52), str(r["is_cached"]).lower(), f"{r['similarity']:.3f}", f"{r['latency_ms']:,.0f}"])
    return rows


def part2_summary_rows() -> List[List[Any]]:
    """Hit rate and average latency table."""
    data = load("part2_results.json")
    rows: List[List[Any]] = [["Measure", "Value"]]
    if not data:
        return rows + [[PENDING, ""]]
    s = data["summary"]
    rows += [
        ["Threshold", s["threshold"]],
        ["Queries / hits / misses", f"{s['queries']} / {s['hits']} / {s['misses']}"],
        ["Cache hit rate", f"{s['hit_rate_pct']}%"],
        ["Average latency, cached", f"{s['avg_latency_cached_ms']} ms"],
        ["Average latency, not cached (HW8 agents)", f"{s['avg_latency_not_cached_ms']} ms"],
    ]
    return rows


def part2_comment() -> str:
    """Describe what happened in the 12-query run, from the numbers."""
    data = load("part2_results.json")
    if not data:
        return "[Write the reading of the Part 2 run here.]"
    rows, s = data["rows"], data["summary"]
    parts = []
    dup = [r for r in rows if r["kind"] == "exact duplicate"]
    para = [r for r in rows if r["kind"] == "paraphrase"]
    parts.append(f"All {sum(r['is_cached'] for r in dup)} of {len(dup)} exact duplicates were served from the cache.")
    parts.append(f"Of the {len(para)} paraphrases, {sum(r['is_cached'] for r in para)} reached the threshold of {s['threshold']}" + (
        "; the others were answered by the agents (their similarity was " + ", ".join(f"{r['similarity']:.3f}" for r in para if not r['is_cached']) + ")." if any(not r['is_cached'] for r in para) else "."))  # fmt: skip
    near = [r for r in rows if r["kind"].startswith("similar")]
    for r in near:
        if r["is_cached"]:
            parts.append(f"Query {r['n']} (a different trial, CT-2026-102) was served from the cache with similarity {r['similarity']:.3f}, so it received the answer written for CT-2026-101. This is a wrong answer from the cache, and Part 3 studies it.")
        else:
            parts.append(f"Query {r['n']} (a different trial, CT-2026-102) scored {r['similarity']:.3f}, below the threshold, so the agents answered it.")
    if s["avg_latency_cached_ms"] and s["avg_latency_not_cached_ms"]:
        parts.append(f"I measured {s['avg_latency_cached_ms']} ms on average for a cached answer against {s['avg_latency_not_cached_ms']} ms for an answer from the agents, which is about {s['avg_latency_not_cached_ms'] / s['avg_latency_cached_ms']:.0f} times as long. This is only what this run showed; the model time varies from run to run.")
    return " ".join(parts)


def sweep_data() -> Optional[Dict[str, Any]]:
    """part3_sweep.json."""
    return load("part3_sweep.json")


def sweep_rows() -> List[List[Any]]:
    """The filled threshold table (3.2)."""
    rows: List[List[Any]] = [["Threshold", "Hit rate", "False-hit rate", "Mean est. end-to-end latency (ms)", "Total cost"]]
    data = sweep_data()
    for i, t in enumerate(config.THRESHOLDS):
        if not data:
            rows.append([f"{t:.2f}", PENDING, "", "", ""])
            continue
        r = data["results"][i]
        rows.append([f"{r['threshold']:.2f}", f"{r['hit_rate_pct']}%", f"{r['false_hit_rate_pct']}%", f"{r['mean_latency_ms']:,.0f}", f"${r['total_cost']:.2f}"])
    return rows


def sweep_detail_rows() -> List[List[Any]]:
    """Counts behind the table: hits, false hits, missed hits, misses."""
    rows: List[List[Any]] = [["Threshold", "Hits", "False hits", "Missed hits (should hit, did not)", "Misses (agent ran)"]]
    data = sweep_data()
    if not data:
        return rows + [["", PENDING, "", "", ""]]
    for r in data["results"]:
        rows.append([f"{r['threshold']:.2f}", 40 - r["misses"], r["false_hits"], r["missed_hits"], r["misses"]])
    return rows


def cost_rows() -> List[List[Any]]:
    """Cost model table (3.4)."""
    rows: List[List[Any]] = [["Threshold", "Misses x $%.2f" % config.COST_MISS, "False hits x $%.2f" % config.COST_FALSE_HIT, "Total cost"]]
    data = sweep_data()
    if not data:
        return rows + [["", PENDING, "", ""]]
    for r in data["results"]:
        rows.append([f"{r['threshold']:.2f}", f"{r['misses']} = ${r['misses'] * config.COST_MISS:.2f}", f"{r['false_hits']} = ${r['false_hits'] * config.COST_FALSE_HIT:.2f}", f"${r['total_cost']:.2f}"])
    return rows


def best_threshold() -> Optional[Dict[str, Any]]:
    """Lowest total cost; on a tie the higher (safer) threshold."""
    data = sweep_data()
    if not data:
        return None
    return min(data["results"], key=lambda r: (r["total_cost"], -r["threshold"]))


def sweep_comment() -> str:
    """Reading of the sweep, from the numbers."""
    data = sweep_data()
    if not data:
        return "[Write the reading of the threshold table here.]"
    res = data["results"]
    first_clean = next((r for r in res if r["false_hits"] == 0), None)
    most = max(res, key=lambda r: r["false_hit_rate_pct"])
    text = f"The lowest threshold ({res[0]['threshold']:.2f}) gave a hit rate of {res[0]['hit_rate_pct']}% but also a false-hit rate of {res[0]['false_hit_rate_pct']}%; the highest ({res[-1]['threshold']:.2f}) gave {res[-1]['hit_rate_pct']}% and {res[-1]['false_hit_rate_pct']}%. "
    if first_clean:
        text += f"The first threshold with no false hit at all was {first_clean['threshold']:.2f}"
        text += f", where {first_clean['missed_hits']} of the 20 cases that should hit were missed. " if first_clean["missed_hits"] else ". "
    else:
        text += f"No threshold removed every false hit (the worst, {most['threshold']:.2f}, had {most['false_hits']}). "
    text += "Mean latency falls as the threshold goes down because more queries are answered from the cache instead of by the agents."
    return text


def choice_text() -> str:
    """The shipped threshold and why, from the cost table."""
    best = best_threshold()
    if not best:
        return "[Choose the threshold after the sweep.]"
    res = sweep_data()["results"]
    at_default = next((r for r in res if abs(r["threshold"] - config.DEFAULT_THRESHOLD) < 1e-9), None)
    text = f"I would ship a threshold of {best['threshold']:.2f}. It has the lowest total cost on my 40 cases (${best['total_cost']:.2f}, with {best['false_hits']} false hits and {best['misses']} agent runs)"
    if at_default and at_default is not best:
        text += f", against ${at_default['total_cost']:.2f} for the starting value {at_default['threshold']:.2f}"
    text += ". "
    if best["false_hits"] == 0:
        text += "It also gives no wrong answer from the cache on this set, which matters more than a few extra agent runs because a wrong answer reaches a user while a miss only costs time. "
    else:
        text += f"It still lets {best['false_hits']} wrong answers through on this set, so I would not treat it as safe for production without a version or entity check next to the similarity score. "
    text += "The choice depends on my two cost numbers: if a false hit were cheap, a lower threshold would win."
    return text


def false_hit_block() -> Optional[Dict[str, Any]]:
    """part3_false_hit.json."""
    return load("part3_false_hit.json")


def confusion_text() -> str:
    """Why the embedding model saw the two queries as similar, from the word difference."""
    d = false_hit_block()
    if not d:
        return "[Explain the embedding confusion after the run.]"
    a, b = d["words_only_in_cached"], d["words_only_in_incoming"]
    text = f"The two queries share almost all of their words. The only words that differ are {a} in the cached query and {b} in the incoming one. "
    text += "A sentence embedding encodes the topic and the shape of the question, here 'ask for one field of one trial'. A change of a single token such as a trial number, or of one attribute word, moves the vector only a little, so the cosine similarity stays high even though the correct answer is different. "
    text += "The model has no notion that two trial codes such as CT-2026-101 and CT-2026-103 are different records or that title and capacity are different facts; to it they are small variations of the same sentence."
    return text


def stale_data() -> Optional[Dict[str, Any]]:
    """part3_stale.json."""
    return load("part3_stale.json")


def stale_rows() -> List[List[Any]]:
    """Step table for 3.5."""
    rows: List[List[Any]] = [["Step", "Database capacity", "is_cached", "Answer returned"]]
    d = stale_data()
    if not d:
        return rows + [[PENDING, "", "", ""]]
    steps = [
        ("1. First ask (miss, answer stored)", d["original"], d["first"]),
        ("2. After UPDATE, no invalidation", d["updated_to"], d["stale_hit"]),
        ("3. After UPDATE, version check on", d["updated_to"], d["after_invalidation"]),
        ("4. Asked again", d["updated_to"], d["warm_hit"]),
    ]
    for name, cap, r in steps:
        rows.append([name, cap, str(r["is_cached"]).lower(), short(r["answer"], 90)])
    return rows


def cases_yaml_text() -> str:
    """cache_cases.yaml as it is committed (without the comment header)."""
    text = config.CASES_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.startswith("#")).strip()


def case_count_rows() -> List[List[Any]]:
    """Small table of the four case types."""
    spec = yaml.safe_load(config.CASES_PATH.read_text(encoding="utf-8"))
    desc = {
        "exact_duplicate": ("same text as a seed query", "hit"),
        "paraphrase": ("same meaning, different words", "hit"),
        "similar_different": ("looks alike, correct answer is different", "miss"),
        "unrelated": ("not about clinical trial listings", "miss"),
    }
    rows: List[List[Any]] = [["Type", "Cases", "Meaning", "Expected"]]
    for t, (meaning, expected) in desc.items():
        rows.append([t, sum(1 for c in spec["cases"] if c["type"] == t), meaning, expected])
    return rows


# ------------------------------------------------------------------- Part 4 data
def revision_data() -> Optional[Dict[str, Any]]:
    """part4_revision_demo.json."""
    return load("part4_revision_demo.json")


def validation_rows() -> List[List[Any]]:
    """Validation outcome per candidate lesson."""
    rows: List[List[Any]] = [["Lesson", "Topic", "Improved", "Regressed", "Unrelated ok", "Decision"]]
    d = load("part4_validation.json")
    if not d:
        return rows + [[PENDING, "", "", "", "", ""]]
    for c in d["candidates"]:
        rows.append([c["lesson_id"], c["topic"], ", ".join(c["improved"]) or "none", ", ".join(c["regressed"]) or "none", str(c["unrelated_ok"]).lower(), c["status"].upper()])
    return rows


def lessons_rows() -> List[List[Any]]:
    """lessons.json as a table."""
    rows: List[List[Any]] = [["lesson_id", "failure_pattern", "created_at", "use_count", "status"]]
    path = config.DATA_DIR / "lessons.json"
    if not path.exists():
        return rows + [[PENDING, "", "", "", ""]]
    for x in json.loads(path.read_text(encoding="utf-8")):
        rows.append([x["lesson_id"], short(x["failure_pattern"], 80), x["created_at"], x["use_count"], x["status"]])
    return rows


def variants_rows() -> List[List[Any]]:
    """The four-variant result table (4.4)."""
    rows: List[List[Any]] = [["Variant", "Correct answers", "Incorrect answers", "Average attempts", "Average latency (ms)"]]
    d = load("part4_final.json")
    for i, name in enumerate(["Baseline", "Evaluator Repair", "Lesson Memory", "Validated Improvement"]):
        if not d:
            rows.append([name, PENDING, "", "", ""])
            continue
        r = d["table"][i]
        rows.append([name, f"{r['correct']} of 16", f"{r['incorrect']} of 16", r["avg_attempts"], f"{r['avg_latency_ms']:,.0f}"])
    return rows


def variants_comment() -> str:
    """Reading of the final table, from the numbers."""
    d = load("part4_final.json")
    if not d:
        return "[Write the reading of the variants table here.]"
    t = {r["variant"]: r for r in d["table"]}
    b, e, m, v = (t[k] for k in ("Baseline", "Evaluator Repair", "Lesson Memory", "Validated Improvement"))
    text = f"Without any feedback the Answering Agent was right on {b['correct']} of 16 test questions. With evaluator repair it was right on {e['correct']}, at {e['avg_attempts']} attempts on average. "
    text += f"Saving every lesson (Lesson Memory) gave {m['correct']} correct at {m['avg_attempts']} attempts, and keeping only validated lessons gave {v['correct']} correct at {v['avg_attempts']} attempts. "
    if m["correct"] < v["correct"] or m["avg_attempts"] > v["avg_attempts"]:
        text += "The unvalidated memory did worse than the validated one, which is the effect the validation step is meant to prevent. "
    elif m["correct"] == v["correct"] and m["avg_attempts"] == v["avg_attempts"]:
        text += "The two lesson variants gave the same result on this test set, so validation did not change the outcome here. "
    text += "Attempts and latency go up together, because every extra attempt is one more model call. Evaluator repair counts a question as correct after the revision, and the revision receives the reference fact in the feedback, so that variant measures how well the model copies a fact it is handed; the first-attempt accuracy of the lesson variants is a fairer sign of learning."
    return text


def first_attempt_rows() -> List[List[Any]]:
    """First-attempt correctness per variant (shows what lessons changed)."""
    rows: List[List[Any]] = [["Variant", "Correct at attempt 1"]]
    d = load("part4_final.json")
    if not d:
        return rows + [[PENDING, ""]]
    for name, results in d["detail"].items():
        rows.append([name, f"{sum(1 for r in results if r['first_result'] == 'PASS')} of {len(results)}"])
    return rows


# ----------------------------------------------------------------------- report
def build(canvas: bool, commit: str) -> Doc:
    """Write the whole report text."""
    PLACED.clear()
    d = Doc()
    d.title("DATA 260: Agentic AI")
    d.centered(
        "Instructor: Prof. Dr. Simon Shim   |   Student Name: Trapti Kulshrestha   |   STUDENT ID: 019124833   |   Homework: 9"
    )
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
    d.label("Local Model: ", "qwen3:8b (Ollama), seed 4833. No hosted API is used.")
    d.label("Embedding model: ", "nomic-embed-text (Ollama), the same model as HW6; 768 dimensions")
    d.label("Cache: ", "Redis Stack (Redis with the RediSearch vector index) in Docker; Python client redis-py")
    if canvas:
        d.label("Tagged commit (tag hw9): ", commit)

    d.h1("Project Setup")
    d.p(
        "HW9 is built on top of HW8 in the same repository, on a hw9-work branch made from the hw8 tag. The new code is in the hw9/ package and a few top-level scripts, so the earlier homework is unchanged. Redis Stack runs from docker-compose.hw9.yml; it is plain Redis plus the search module, which is what gives me a vector index. Kafka is not needed for HW9."
    )
    d.p(
        "Two choices are worth stating. First, the cache sits at the ingress in front of the HW8 agent pipeline. On a miss the request follows the HW8 agent path with the local model through the adapter, as the assignment describes: it reuses the same Planner, Writer and Reviewer implementation (hw8/pipeline.py), the local qwen3:8b adapter, the same retry behaviour and the same approval rule of a review score of at least 6. For the cache experiments I call those existing HW8 stages through an in-process adapter instead of sending the question over the Kafka topics, so that Kafka transport latency does not distort the cache and threshold measurements. The agent behaviour itself is unchanged; only the transport between the stages is not used. Second, the Part 1 counter needs a place in the database, so migrate_hw09.py adds one column, view_count (INT, default 0), to the clinical_trials table of s4833_rel. models.py and the HW4 to HW8 code are untouched, and the script can drop the column again."
    )

    d.h1("Part 1 - Redis View Counter")
    d.p(
        "My primary entity is the clinical trial. The method increment_clinical_trial_views(trial_id) lives on the ClinicalTrialCache class, which holds the Redis client and the database connection. It does three things. It increments the Redis key s4833:views:clinical_trial:<id> with INCR, which is atomic, so two requests at the same time cannot lose a count and no database read is needed. When the new count is a multiple of 10 it writes the count into the view_count column of that trial's row and logs 'Synced views to database'. Then it returns the count."
    )
    d.figs("code_counter")
    d.p(
        f"The demo resets the counter and makes 25 accesses to trial CT-2026-101. The output has the shape the assignment shows: the total goes up by one each time, and the sync line appears after #10 and after #20 ({ref('counter_a')} and {ref('counter_b')}). "
        + part1_text()
        + f" {ref('counter_db')} checks the two places directly."
    )
    d.figs("counter_a", "counter_b", "counter_db")
    d.p(
        "The price of this speed is that the database can be up to nine views behind. If Redis lost its data between two syncs, those views would be gone. For a view counter that is acceptable; for something like a payment it would not be."
    )

    d.h1("Part 2 - Semantic Response Cache")
    d.p(
        "The cache is in front of the question endpoint (QAService.answer in hw9/qa_service.py). For every query it takes a timestamp, embeds the text with nomic-embed-text, and asks Redis for the nearest stored query. Each cache entry is a Redis hash under s4833:semcache:<id> with the query, its embedding, the final answer, a data-version marker and the time it was stored. The index s4833:idx:semcache is a FLAT (exact) vector index on the embedding with cosine distance; similarity is one minus that distance. I used FLAT because the cache holds only a few dozen entries, so an approximate index would add complexity for no gain."
    )
    d.p(
        "If the best match has a similarity at or above the threshold (0.85 to start with), the stored answer is returned with is_cached=true, the similarity and the latency, and a HIT line is logged. Otherwise a MISS line is logged, the HW8 agents run, the answer is stored with its embedding and a data-version marker, and the answer is returned with is_cached=false. Only answers that the Reviewer approved are stored. If a question names a trial code (CT-2026-101 and so on), the agents are given that trial's row from the database as facts, and the marker is a short hash of that row; questions without a trial code get the marker 'static'."
    )
    d.figs("code_cache", "code_qa", "index_info")
    d.p(
        f"I sent 12 queries: new questions, exact duplicates, paraphrases, one unrelated question and one question about a different trial ({ref('part2_a')} and {ref('part2_b')}). The table gives the flag, the similarity and the latency of each."
    )
    d.figs("part2_a", "part2_b")
    d.table(part2_rows(), [0.3, 1.2, 2.5, 0.7, 0.8, 0.8])
    d.table(part2_summary_rows(), [3.2, 2.4])
    d.p(part2_comment())

    d.h1("Part 3 - Threshold Economics and Stale Answers")
    d.h2("3.1 Labeled test set")
    d.p(
        "cache_cases.yaml contains 40 labeled evaluation cases (10 in each required category), plus 10 separate seed queries that are used to fill the cache before every run. I wrote and fixed the labels before I ran any sweep and did not change them afterwards. The seeds mix questions that depend on a database row (the capacity and title of trials) with questions about the platform rules (field lengths, required fields, the retry rule). The tricky group is 'similar but different': for example the capacity of CT-2026-102 against the cached capacity of CT-2026-101, or the maximum length of a trial category against the cached length of a trial title. A good cache must not return the stored answer for these. The full file is in the appendix."
    )
    d.table(case_count_rows(), [1.6, 0.6, 3.0, 0.9])
    d.figs("cases_yaml")
    d.h2("3.2 Threshold sweep")
    d.p(
        "For each of the five thresholds I filled the cache with the ten seed answers and sent the 40 cases one at a time against it. The cache is read-only during a case run, so every case is judged against the same ten entries. The hit rate is hits divided by 40. The false-hit rate is the number of hits among the 20 cases that should miss, divided by 20. The mean latency per case is the real time of the embedding call and the Redis search, plus, for a miss, the time the HW8 agents needed for that query. Each distinct query was run through the agents once beforehand and its latency recorded, so the five thresholds are compared on the same agent times and the sweep does not need a hundred model runs; the embedding and the Redis search are measured live every time."
    )
    d.figs("sweep")
    d.table(sweep_rows(), [1.0, 1.0, 1.2, 1.5, 1.0])
    d.p("For comparability, the miss-side agent latency was recorded once per distinct query and reused across thresholds; the embedding and Redis-search latency were measured live for every threshold run. The mean latency is therefore an estimate of end-to-end latency, not five separate wall-clock experiments.")
    d.table(sweep_detail_rows(), [1.0, 0.7, 0.9, 2.3, 1.2])
    d.p(sweep_comment())
    d.h2("3.3 One false hit in full")
    fh = false_hit_block()
    if fh:
        c = fh["case"]
        d.p(
            f"This is the false hit with the highest similarity at the threshold {fh['threshold']} (case {c['id']}, a '{c['type']}' case). It is the clearest example of the cache answering the wrong question."
        )
        d.bullets(
            [
                f"Cached query: {c['matched_query']}",
                f"Incoming query: {c['query']}",
                f"Similarity: {c['similarity']}",
                f"Cached answer that was returned: {c['cached_answer']}",
                f"Correct answer (from the HW8 agents on the incoming query): {fh['correct_answer']}",
            ]
        )
    else:
        d.p(PENDING)
    d.figs("false_hit")
    d.p(confusion_text())
    d.h2("3.4 Cost model and threshold choice")
    d.p(
        f"I use two costs. A cache miss costs ${config.COST_MISS:.2f}: it is one full agent run (a planner, a writer and a reviewer call, roughly 1,000 tokens at the price of a hosted model of this size) and the user waits for it. My own model runs locally and costs no money, so I priced it as what the same tokens would cost on a hosted API. A false hit costs ${config.COST_FALSE_HIT:.2f}: a wrong listing answer reaches a user instantly and somebody has to notice, correct it and possibly handle a support request or a wrong decision about a trial. I set it 100 times the miss cost because the cost of one wrong answer in a clinical setting is mostly human time and trust, not tokens. Both numbers are assumptions; the table shows how the choice depends on them. The total cost at a threshold is (cache misses x miss cost) + (false hits x false-hit cost) over the 40 cases. A hit that is correct costs nothing, and a missed hit simply counts as a miss."
    )
    d.table(cost_rows(), [1.0, 1.9, 2.0, 1.0])
    d.p(choice_text())
    d.h2("3.5 Stale answers and invalidation")
    d.p(
        "I chose the cached question 'What is the participant capacity of trial CT-2026-101?'. Its answer depends on one row of s4833_rel.clinical_trials, the row with trial_code CT-2026-101. The steps were: ask once so the answer is cached; update the record (participant_capacity from its original value to 120); ask again with no invalidation; then ask again with invalidation switched on; and finally put the original value back. "
        + f"{ref('stale_a')} shows the stale hit and {ref('stale_b')} shows the invalidation."
    )
    d.figs("stale_a")
    d.p(
        "The strategy I implemented uses the data-version marker. When an answer is stored it gets a marker, a short hash of the content fields of the rows it was built from (title, sponsor, capacity, organisation, category). When the cache finds a hit, QAService compares the stored marker with the marker that the database gives now. If they differ, the entry is deleted, the agents answer again from the current row, and the new answer is stored with the new marker."
    )
    d.figs("code_stale", "stale_b")
    d.table(stale_rows(), [2.3, 0.9, 0.7, 2.9])
    d.p(
        "The trade-off is a database read on every hit. A hit is still much cheaper than an agent run, but it is no longer free, and the cache now depends on the database being reachable. The alternative, deleting entries when a record is updated, costs nothing on a hit but only works if every code path that changes the record remembers to do it; an update made by hand in MySQL, as I did here, would be missed. A time-to-live would be the simplest option but allows stale answers until it expires. A version check is correct whenever the marker covers all the data the answer used, which is why I chose it. It cannot protect an answer that depends on something I did not put into the marker."
    )

    d.h1("Part 4 - Self-Improving Multi-Agent System")
    d.h2("Setup")
    d.p(
        "The two agents are an Answering Agent and an Evaluator Agent. The Answering Agent is qwen3:8b with a short system prompt and, when there are lessons, a list of lessons added to that prompt. It has no access to the reference data, like an ordinary support assistant that knows nothing about my platform. The Evaluator Agent compares an answer with the reference dataset (data/hw09/reference_data.json). I wrote the reference dataset from my own system: the field-length limits of a trial listing from the HW8 validation code, the retry, dead-letter and offset rules of the HW8 agents, the capacity and title of the five sample trials in the s4833_rel table, and a few things the listings do not hold at all (phase, principal investigator, dates). The three input files training_data.json (12 questions), validation_data.json (12) and test_data.json (16) contain only questions, with an id. A test-only check in my offline tests confirms that every question matches one reference entry."
    )
    d.p(
        "The Evaluator does not call a model. For each question it finds the reference entry the question is about (keyword groups), then checks that the answer contains the reference value, for example 2000 for the length of a description, 255 for the title. For a value the listings do not hold, the answer has to say that it is not available. For a question that has nothing to do with the listings, the answer must not contain listing facts. I made the Evaluator rule-based so that its verdict is the same every time and does not depend on a second model's mood; the cost is that it can only judge what the reference covers (see the limitation below)."
    )
    d.figs("code_answering", "code_evaluator", "ref_data")
    d.h2("4.1 Repair failed answers using evaluator feedback")
    d.p(
        "The workflow is: the Answering Agent answers; the Evaluator returns PASS or REVISE, a short explanation and, for REVISE, feedback that quotes the reference fact; the Answering Agent writes a revised answer from the feedback; the Evaluator checks the revision; the system returns the final answer and the final evaluation. There are at most two answers. After the second one the system stops and reports whatever the result is, even if it is still REVISE."
    )
    rv = revision_data()
    if rv:
        d.p(
            "To show the whole sequence reliably I made one controlled test case in which the first answer is replaced by an intentionally incomplete one. Everything after that is real model output."
        )
        d.bullets(
            [f"Question: {rv['question']}"]
            + [
                f"Attempt {a['attempt']} answer: {a['answer']} | Evaluator: {a['result']}. {a['explanation']}"
                + (f" Feedback: {a['feedback']}" if a["feedback"] else "")
                for a in rv["attempts"]
            ]
            + [
                f"Number of attempts: {rv['attempt_count']}",
                f"Final evaluation: {rv['final_result']}",
                f"Final response: {rv['final_answer']}",
            ]
        )
    else:
        d.p(PENDING)
    d.figs("revision")
    d.h2("4.2 Save and reuse lessons")
    d.p(
        "I ran the training questions through the repair workflow. When the same failure pattern shows up at least twice (the Evaluator groups failures by the topic of the reference entry), it proposes a lesson with the pattern and a correction. The correction repeats the reference facts of the entries that failed, so a lesson teaches the exact values it was created from and nothing else. Lessons are saved in lessons.json with lesson_id, failure_pattern, correction, created_at and use_count (and, for bookkeeping, topic, status and source). Before it answers, the Answering Agent loads the lessons that share a content word with the question and adds their corrections to its prompt; use_count goes up for each lesson loaded. A question with no shared word, such as one about the capital of a country, loads no lesson."
    )
    d.figs("train")
    d.table(lessons_rows(), [0.9, 3.2, 0.9, 0.7, 0.8])
    d.figs("lessons_json")
    ru = load("part4_lesson_reuse.json")
    if ru:
        w = ru["without_lessons"]["attempts"][0]
        r1 = ru["with_lessons"]["attempts"][0]
        d.p(
            f"The reuse example is a later question that was not in the training set: '{ru['question']}'. Without lessons the agent answered '{short(w['answer'], 160)}' (evaluation {w['result']}). With the stored lessons loaded ({', '.join(ru['loaded']) or 'none'}) it answered '{short(r1['answer'], 160)}' (evaluation {r1['result']})."
        )
    else:
        d.p(PENDING)
    d.figs("reuse")
    d.h2("4.3 Validate improvements before keeping them")
    d.p(
        "A lesson can also do harm, for example by making the agent refuse a question it used to answer correctly. So each candidate lesson is tested on validation_data.json before it is kept. I run the validation questions on the first answer only, so the lesson is judged on its own and not hidden by the repair loop, once without the new lesson and once with it (together with the lessons already kept). A lesson is kept only if no previously correct answer becomes wrong and the unrelated questions still get no listing facts; a lesson that fixes nothing but breaks nothing is allowed by the assignment and kept. The last candidate is a rule I wrote on purpose to be bad (it tells the agent that information about trials is confidential), added to prove that a harmful lesson is rejected. It is marked controlled_test in lessons.json and is not a pattern the Evaluator found."
    )
    d.figs("validate")
    d.table(validation_rows(), [0.9, 1.4, 1.2, 1.2, 0.9, 0.9])
    d.h2("4.4 Four system variants")
    d.p(
        "The final test uses test_data.json, which was not used to create or choose any lesson, and the file was not changed between the four runs. Baseline is the Answering Agent alone, one answer. Evaluator Repair adds the Evaluator and one revision. Lesson Memory is Evaluator Repair plus every lesson that the training run saved, with no validation. Validated Improvement is Evaluator Repair plus only the lessons that passed validation."
    )
    d.figs("final")
    d.table(variants_rows(), [1.7, 1.2, 1.3, 1.2, 1.4])
    d.table(first_attempt_rows(), [3.0, 2.0])
    d.p(variants_comment())
    d.h2("Agent communication, stopping, validation and a limitation")
    d.bullets(
        [
            "Agent communication: the two agents exchange small dictionaries. The Answering Agent sends {question, answer, attempt}; the Evaluator replies {result, explanation, feedback}. Both directions are logged, as in the revision output above.",
            "Lesson reuse: before every first attempt the Answering Agent loads the lessons that share a content word with the question, adds their corrections to its prompt, and increments use_count. The same lessons stay loaded for the revision.",
            "Stopping condition: the loop ends as soon as the Evaluator says PASS, or after the second answer, whichever comes first. The result of the second answer is reported as it is.",
            "Validation process: for each candidate the validation set is run without and with the lesson; the lesson is kept only if nothing that was correct becomes wrong and unrelated questions stay clean. The test set is touched only once, at the end.",
            "Limitation: the Evaluator can only judge questions that map to an entry in my reference dataset, and the lessons only contain the values of entries that failed in training. They therefore help paraphrases of questions seen in training, not new facts, and a bigger domain would need a retrieval step and a better matcher than my keyword groups. The test set is small (16 questions), so a difference of one question is not strong evidence.",
        ]
    )

    d.h1("Self-check")
    d.p(
        "make verify-hw09 runs verify_hw09.py. It checks that Redis Stack has the search module, that the embedding model and the database answer, the counter (it counts, the key starts with s4833: and the database is synced at ten), the vector index (an exact duplicate scores about 1.0), the 40 labeled cases, the stale-then-invalidate behaviour, the Part 4 files and the lessons.json fields, the four-variant results file and the offline tests, and writes reports/hw09/verification.json ("
        + ref("verify")
        + "). Temporary changes to the database are put back. The agents in this check use a stub model; the measurements in the report come from qwen3:8b."
    )
    d.figs("verify")

    d.h1("AI Use")
    ai = (OUT / "AI_USE.md").read_text(encoding="utf-8") if (OUT / "AI_USE.md").exists() else ""
    for block in ai.split("\n## ")[1:]:
        heading, _, body = block.partition("\n")
        d.h2(heading.strip())
        for para in body.split("\n\n"):
            para = para.strip()
            if para and not para.startswith("<!--"):
                d.p(para.replace("`", ""))

    d.page_break()
    d.h1("Appendix: cache_cases.yaml")
    d.code(cases_yaml_text(), "cache_cases.yaml (committed before the first sweep)")
    assert PLACED == ORDER, f"figure order mismatch: {PLACED}"
    return d


def to_pdf(docx_path: Path) -> Optional[Path]:
    """Convert with LibreOffice if it is installed."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("LibreOffice not found: open the .docx in Word and export to PDF.")
        return None
    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(docx_path.parent),
            str(docx_path),
        ],
        check=True,
        capture_output=True,
    )
    return docx_path.with_suffix(".pdf")


def main() -> None:
    """Build the Git copy, and the Canvas copy when --commit is given."""
    parser = argparse.ArgumentParser(description="Build the HW9 report")
    parser.add_argument("--commit", default="", help="hw9 tag commit hash (Canvas copy)")
    parser.add_argument("--list-screenshots", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()
    if args.list_screenshots:
        for number, key in enumerate(ORDER, 1):
            have = bool(list(SHOTS.glob(f"{key}.*")) + list(SHOTS.glob(f"*_{key}.*")))
            caption, how = FIGS[key]
            print(f"{'[x]' if have else '[ ]'} {number:02d}_{key}.png  {caption}\n        {how}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(False, "", "Report_editable.docx", "Report.pdf")]
    if args.commit:
        jobs.append((True, args.commit, "Kulshrestha_HW9_editable.docx", "Kulshrestha_HW9.pdf"))
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
