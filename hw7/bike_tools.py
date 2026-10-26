"""The three tools for the Bay Wheels agent (HW7 Part 4).

Every tool returns the same envelope:
  {"success": bool, "data": ..., "error": str, "source": str, "ts": str}
"""

from __future__ import annotations

import ast
import csv
import math
import operator
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hw7 import bike_policy

CSV_SOURCE = "uploaded.csv"
MAX_ROWS = 50
MAX_PASSAGE_CHARS = 240
CALC_PATTERN = re.compile(r"^[0-9+\-*/().\s]+$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BLOCKED_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|"
    r"vacuum|reindex|analyze|begin|commit|rollback|savepoint)\b",
    re.IGNORECASE,
)


def envelope(
    success: bool,
    data: Any = None,
    error: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """The common result shape used by all three tools."""
    out: Dict[str, Any] = {
        "success": success,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if data is not None:
        out["data"] = data
    if error is not None:
        out["error"] = error
    if source is not None:
        out["source"] = source
    return out


# --------------------------------------------------------------------------
# JSON schemas (inputs are pydantic models, outputs are plain dicts)
# --------------------------------------------------------------------------


class CsvSqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(description="One read-only SELECT over table trips or view rides")


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(description="Pricing page URL")
    query: str = Field(description="What to look for on the page")
    k: Optional[int] = Field(default=5, ge=1, le=10, description="Passages to return")


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(description="Arithmetic using digits and + - * / ( ) .")
    units: Optional[str] = Field(default=None, description="Optional unit label")


INPUT_MODELS = {
    "csv_sql": CsvSqlInput,
    "policy_retriever": PolicyInput,
    "calculator": CalculatorInput,
}

_ENVELOPE = {
    "success": {"type": "boolean"},
    "error": {"type": "string"},
    "source": {"type": "string"},
    "ts": {"type": "string"},
}

OUTPUT_SCHEMAS = {
    "csv_sql": {
        "type": "object",
        "properties": {
            **_ENVELOPE,
            "data": {
                "type": "object",
                "properties": {
                    "rows": {"type": "array", "items": {"type": "object"}},
                    "row_count": {"type": "number"},
                    "source": {"const": CSV_SOURCE},
                },
                "required": ["rows", "row_count", "source"],
            },
        },
        "required": ["success"],
    },
    "policy_retriever": {
        "type": "object",
        "properties": {
            **_ENVELOPE,
            "data": {
                "type": "object",
                "properties": {
                    "passages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "source": {"type": "string"},
                                "score": {"type": "number"},
                            },
                            "required": ["text", "source", "score"],
                        },
                    }
                },
                "required": ["passages"],
            },
        },
        "required": ["success"],
    },
    "calculator": {
        "type": "object",
        "properties": {
            **_ENVELOPE,
            "data": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "units": {"type": "string"},
                },
                "required": ["value"],
            },
        },
        "required": ["success"],
    },
}


def tool_schemas() -> Dict[str, Dict[str, Any]]:
    """Input and output JSON schema for each tool."""
    return {
        name: {
            "input": model.model_json_schema(),
            "output": OUTPUT_SCHEMAS[name],
        }
        for name, model in INPUT_MODELS.items()
    }


# --------------------------------------------------------------------------
# csv_sql
# --------------------------------------------------------------------------

VIEW_SQL = """
CREATE VIEW rides AS
SELECT ride_id, rideable_type, started_at, ended_at, member_casual,
       {rider} AS synthetic_rider_id,
       duration_min, week, is_ebike,
       CASE WHEN is_ebike = 0 THEN duration_min ELSE 0 END AS classic_min,
       CASE WHEN is_ebike = 1 THEN duration_min ELSE 0 END AS ebike_min
FROM (
  SELECT *,
         ROUND((julianday(ended_at) - julianday(started_at)) * 1440.0, 2)
           AS duration_min,
         strftime('%W', started_at) AS week,
         CASE WHEN rideable_type LIKE 'electric%' THEN 1 ELSE 0 END AS is_ebike
  FROM trips
)
"""


def check_read_only(sql: str) -> str:
    """Tool defense: accept one SELECT only. Returns the cleaned statement."""
    text = (sql or "").strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    if not text:
        raise ValueError("empty SQL")
    if ";" in text:
        raise ValueError("only one statement is allowed")
    if "--" in text or "/*" in text:
        raise ValueError("SQL comments are not allowed")
    if not re.match(r"^select\b", text, re.IGNORECASE):
        raise ValueError("only SELECT statements are allowed")
    word = BLOCKED_SQL.search(text)
    if word:
        raise ValueError(f"'{word.group(0).lower()}' is not allowed (read-only)")
    return text


def _authorizer(action: int, *_args: Any) -> int:
    allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION)
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


class TripDB:
    """The uploaded trip CSV loaded into an in-memory SQLite database."""

    def __init__(self, csv_path: str, read_only: bool = True) -> None:
        self.read_only = read_only
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.columns: List[str] = []
        self.events: List[Dict[str, Any]] = []  # every statement sent to csv_sql
        self.row_count = self._load(csv_path)
        if read_only:
            # Second layer: SQLite itself refuses anything but reads.
            self.conn.execute("PRAGMA query_only = ON")
            self.conn.set_authorizer(_authorizer)

    def _load(self, csv_path: str) -> int:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            for name in header:
                if not IDENT.match(name):
                    raise ValueError(f"unsupported column name: {name!r}")
            self.columns = header
            cols = ", ".join(f"{c} TEXT" for c in header)
            self.conn.execute(f"CREATE TABLE trips ({cols})")
            marks = ", ".join("?" for _ in header)
            rows = ([v if v != "" else None for v in r] for r in reader)
            self.conn.executemany(f"INSERT INTO trips VALUES ({marks})", rows)
        rider = "synthetic_rider_id" if "synthetic_rider_id" in header else "NULL"
        self.conn.execute(VIEW_SQL.format(rider=rider))
        self.conn.commit()
        return int(self.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0])

    def current_rows(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0])

    def _record(self, sql: str, executed: bool, error: str = "") -> None:
        is_select = bool(re.match(r"^\s*select\b", sql or "", re.IGNORECASE))
        self.events.append(
            {
                "sql": (sql or "")[:200],
                "kind": "select" if is_select else "write",
                "executed": executed,
                "error": error,
            }
        )

    def query(self, sql: str) -> Dict[str, Any]:
        if self.read_only:
            try:
                clean = check_read_only(sql)
                cur = self.conn.execute(clean)
            except (ValueError, sqlite3.Error) as exc:
                self._record(sql, False, str(exc))
                raise
            self._record(sql, True)
        else:
            cur = self._run_unchecked(sql)
            self._record(sql, True)
        names = [d[0] for d in cur.description or []]
        fetched = cur.fetchmany(MAX_ROWS + 1)
        rows = [dict(zip(names, r)) for r in fetched[:MAX_ROWS]]
        return {
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(fetched) > MAX_ROWS,
            "source": CSV_SOURCE,
        }

    def _run_unchecked(self, sql: str) -> sqlite3.Cursor:
        """Used only to show the attack before the defence is switched on."""
        cur = self.conn.cursor()
        for part in [p for p in sql.split(";") if p.strip()]:
            cur = self.conn.execute(part)
        self.conn.commit()
        return cur


def csv_sql(db: TripDB, sql: str) -> Dict[str, Any]:
    try:
        return envelope(True, db.query(sql), source=CSV_SOURCE)
    except (ValueError, sqlite3.Error) as exc:
        return envelope(False, error=f"{type(exc).__name__}: {exc}", source=CSV_SOURCE)


# --------------------------------------------------------------------------
# policy_retriever
# --------------------------------------------------------------------------

PLAN_NAMES = ["Single ride", "Day pass", "Month pass", "Lyft Bike", "Lyft Pink"]
STOP_WORDS = {
    "the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "is", "are",
    "what", "how", "much", "does", "do", "per", "with", "any", "all",
}  # fmt: skip
SYNONYMS = {
    "membership": ["month", "annual", "pass"],
    "monthly": ["month"],
    "pay": ["single", "ride"],
    "unlock": ["unlocks", "unlock"],
    "ebike": ["ebikes", "ebike"],
    "e-bike": ["ebike", "ebikes"],
    "included": ["free", "unlimited"],
    "overage": ["then", "extra", "min"],
    "surcharge": ["then", "extra", "min"],
}
PRICE_LINE = re.compile(r"^\$[\d.,]+(/\w+)?$")
SECTION_HEADERS = {"Classic bike prices": "Classic bike", "Ebike prices": "Ebike"}


def _plan_prices(lines: List[str]) -> Dict[str, str]:
    """Plan name -> price, from the plan list near the top of the page."""
    for i, line in enumerate(lines):
        if line == PLAN_NAMES[0] and lines[i + 1 : i + 3] == ["Day pass", "Month pass"]:
            prices = [x for x in lines[i + 1 : i + 14] if PRICE_LINE.match(x)]
            if len(prices) >= len(PLAN_NAMES):
                return dict(zip(PLAN_NAMES, prices))
    return {}


def build_passages(text: str, url: str) -> List[Dict[str, Any]]:
    """Cut the page text into short, quotable passages."""
    lines = bike_policy.split_lines(text)
    out: List[Dict[str, Any]] = []
    seen = set()

    def add(passage: str, note: Optional[str] = None) -> None:
        passage = passage[:MAX_PASSAGE_CHARS]
        if passage not in seen:
            seen.add(passage)
            item: Dict[str, Any] = {"text": passage, "source": url}
            if note:
                item["note"] = note
            out.append(item)

    prices = _plan_prices(lines)
    for name, price in prices.items():
        add(f"{name}: {price}")
    plan_order = list(prices) if prices else []
    for i, line in enumerate(lines):
        if line in SECTION_HEADERS and plan_order:
            block = lines[i + 1 : i + 1 + len(plan_order)]
            for plan, rate in zip(plan_order, block):
                add(
                    f"{SECTION_HEADERS[line]} - {plan}: {rate}",
                    "plan label inferred from the order of the plan list",
                )
    for line in lines:
        if len(line) > 40 and re.search(r"\$|min|unlock|unlimited", line):
            add(line)
    return out


def _terms(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9$.\-]+", text.lower())
    terms: List[str] = []
    for w in words:
        if w in STOP_WORDS:
            continue
        terms.append(w)
        terms.extend(SYNONYMS.get(w, []))
    return terms


def score_passage(query_terms: List[str], passage: str) -> float:
    ptext = passage.lower().replace("-", " ")
    words = set(re.findall(r"[a-z0-9$.]+", ptext))
    hits = sum(1 for t in set(query_terms) if t.replace("-", " ") in words)
    return round(hits / math.sqrt(1 + len(words)), 3) if hits else 0.0


def policy_retriever(
    url: str,
    query: str,
    k: int = 5,
    fetch: Callable[[str], Dict[str, str]] = bike_policy.fetch_page,
) -> Dict[str, Any]:
    try:
        page = fetch(url)
    except Exception as exc:  # network, bad URL, missing file
        return envelope(False, error=f"fetch failed: {exc}", source=url)
    passages = build_passages(page["text"], url)
    terms = _terms(query)
    for p in passages:
        p["score"] = score_passage(terms, p["text"])
    ranked = sorted(passages, key=lambda p: -p["score"])
    top = [p for p in ranked if p["score"] > 0][: max(1, min(int(k or 5), 10))]
    if not top:
        return envelope(False, error="no passage matched the query", source=url)
    return envelope(True, {"passages": top}, source=url)


# --------------------------------------------------------------------------
# calculator
# --------------------------------------------------------------------------

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    raise ValueError("unsupported expression")


def calculator(expression: str, units: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(expression, str) or not CALC_PATTERN.match(expression):
        return envelope(False, error="expression may only use 0-9 + - * / ( ) .")
    try:
        value = _eval(ast.parse(expression.strip(), mode="eval"))
    except ZeroDivisionError:
        return envelope(False, error="division by zero")
    except (SyntaxError, ValueError):
        return envelope(False, error="could not evaluate the expression")
    data: Dict[str, Any] = {"value": round(value, 6)}
    if units:
        data["units"] = units
    return envelope(True, data)


# --------------------------------------------------------------------------
# One object the agent calls
# --------------------------------------------------------------------------


class BikeTools:
    """Holds the open CSV and the pricing pages fetched during one run."""

    def __init__(
        self,
        csv_path: str,
        fetch: Callable[[str], Dict[str, str]] = bike_policy.fetch_page,
        read_only: bool = True,
    ) -> None:
        self.db = TripDB(csv_path, read_only=read_only)
        self._fetch = fetch
        self.pages: Dict[str, Dict[str, str]] = {}

    def _cached_fetch(self, url: str) -> Dict[str, str]:
        # One snapshot per URL per run, so the hash matches what the agent read.
        if url not in self.pages:
            self.pages[url] = self._fetch(url)
        return self.pages[url]

    def call(self, name: str, inputs: Any) -> Dict[str, Any]:
        model = INPUT_MODELS.get(name)
        if model is None:
            return envelope(False, error=f"unknown tool {name!r}")
        try:
            args = model.model_validate(inputs)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(x) for x in first["loc"]) or "inputs"
            return envelope(False, error=f"bad inputs: {where}: {first['msg']}")
        if name == "csv_sql":
            return csv_sql(self.db, args.sql)
        if name == "policy_retriever":
            return policy_retriever(
                args.url, args.query, args.k or 5, self._cached_fetch
            )
        return calculator(args.expression, args.units)
