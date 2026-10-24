"""Build the HW7 report PDF from real screenshots, real code and the raw data files.

Build:      python build_hw07_report.py --commit <hash>
Checklist:  python build_hw07_report.py --list-screenshots

Screenshots go in reports/hw07/screenshots/ (png or jpg) with the names from
--list-screenshots. A missing screenshot becomes a clearly labelled empty slot;
nothing is invented. Parts that are not finished yet are left out of the PDF.
"""

import argparse
import ast
import json
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from hw7 import config

ROOT = config.REPO_ROOT
OUT_DIR = ROOT / "reports" / "hw07"
SHOT_DIR = OUT_DIR / "screenshots"
RAW_DIR = OUT_DIR / "raw"
NAME = "Trapti Kulshrestha"
REPO_URL = "https://github.com/Psycoder0611/data260-4833"
PAGE_WIDTH = letter[0] - 1.6 * inch

TITLE = ParagraphStyle(
    "Title", fontName="Helvetica", fontSize=24, leading=28, alignment=TA_CENTER
)
SUB = ParagraphStyle(
    "Sub",
    fontName="Helvetica",
    fontSize=13,
    leading=17,
    alignment=TA_CENTER,
    textColor=colors.HexColor("#555555"),
)
H1 = ParagraphStyle(
    "H1",
    fontName="Helvetica-Bold",
    fontSize=14,
    leading=18,
    spaceBefore=14,
    spaceAfter=6,
    keepWithNext=1,
)
H2 = ParagraphStyle(
    "H2",
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=15,
    spaceBefore=10,
    spaceAfter=4,
    keepWithNext=1,
)
BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=11,
    leading=14.5,
    spaceAfter=5,
    alignment=TA_LEFT,
)
LABEL = ParagraphStyle(
    "Label", parent=BODY, fontName="Helvetica-Bold", spaceBefore=6, keepWithNext=1
)
CAPTION = ParagraphStyle(
    "Caption",
    fontName="Helvetica-Oblique",
    fontSize=9.5,
    leading=12,
    spaceAfter=8,
    textColor=colors.HexColor("#444444"),
)
CODE = ParagraphStyle(
    "Code",
    fontName="Courier",
    fontSize=7.6,
    leading=9.4,
    backColor=colors.HexColor("#f3f4f6"),
    borderPadding=5,
    spaceBefore=4,
    spaceAfter=8,
)
CELL = ParagraphStyle("Cell", fontName="Helvetica", fontSize=9.5, leading=12)

# key -> (caption, how to capture it)
SCREENSHOTS = {
    "p1_users_table": (
        "init_hw7_db.py creates the users table with hashed passwords",
        "Terminal: name echo, then `python init_hw7_db.py`.",
    ),
    "p1_login": (
        "Successful login returns a JWT; wrong password returns 401",
        "Terminal (server running): name echo, `python demo_hw07_part1.py login`.",
    ),
    "p1_me_no_token": (
        "GET /auth/me without a token returns 401",
        "Terminal: name echo, `python demo_hw07_part1.py me`.",
    ),
    "p1_me_invalid": (
        "GET /auth/me with an invalid and an expired token returns 401",
        "Terminal: name echo, `python demo_hw07_part1.py badtoken`.",
    ),
    "p1_create": (
        "Create: reader gets 403, writer gets 201",
        "Terminal: name echo, `python demo_hw07_part1.py create`.",
    ),
    "p1_delete": (
        "Delete: writer gets 403, moderator gets 200",
        "Terminal: name echo, `python demo_hw07_part1.py delete`.",
    ),
    "p1_list": (
        "List with a valid token returns 200",
        "Terminal: name echo, `python demo_hw07_part1.py list`.",
    ),
    "p1_lint": (
        "Ruff error, pre-commit hook run, fix, and successful commit",
        "Terminal: follow the lint steps from the handoff note; capture all of it.",
    ),
}


# ------------------------------------------------------------- helpers


def para(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    """Make a paragraph; text is escaped and **x** makes bold."""
    parts = escape(text).split("**")
    safe = "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
    return Paragraph(safe, style)


def wrap_code(text: str, width: int = 100) -> str:
    """Hard-wrap long code lines so they stay inside the page."""
    lines = []
    for line in text.splitlines():
        if len(line) <= width:
            lines.append(line)
        else:
            indent = len(line) - len(line.lstrip())
            lines += textwrap.wrap(
                line,
                width,
                subsequent_indent=" " * (indent + 4),
                break_long_words=True,
            )
    return "\n".join(lines)


def code_function(path: str, name: str, max_lines: int = 48) -> Preformatted:
    """Show the source of one function or class, straight from the file."""
    source = (ROOT / path).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            lines = source.splitlines()[start - 1 : node.end_lineno]
            if len(lines) > max_lines:
                lines = lines[: max_lines - 1] + ["    # ... (shortened)"]
            return Preformatted(wrap_code(f"# {path}\n" + "\n".join(lines)), CODE)
    return Preformatted(f"# {path}: {name} not found", CODE)


def code_lines(path: str, start: int, end: int) -> Preformatted:
    """Show a line range of a text file."""
    file = ROOT / path
    if not file.exists():
        return Preformatted(f"# {path} does not exist yet", CODE)
    lines = file.read_text(encoding="utf-8").splitlines()[start - 1 : end]
    header = f"# {path} (lines {start}-{end})\n"
    return Preformatted(wrap_code(header + "\n".join(lines)), CODE)


def find_shot(key: str):
    """Return the screenshot path for key, or None."""
    for extension in ("png", "jpg", "jpeg"):
        candidate = SHOT_DIR / f"{key}.{extension}"
        if candidate.exists():
            return candidate
    return None


def shot(key: str, numbering: list, missing: list) -> KeepTogether:
    """Return a screenshot (or a labelled empty slot) with its caption."""
    caption, how = SCREENSHOTS[key]
    numbering[0] += 1
    label = f"Figure {numbering[0]} - {caption}"
    path = find_shot(key)
    if path is None:
        missing.append(key)
        box = Table(
            [[para(f"SCREENSHOT NEEDED: {key}.png", CELL)], [para(how, CELL)]],
            colWidths=[PAGE_WIDTH],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#b45309")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        return KeepTogether([box, para(label, CAPTION)])
    with PilImage.open(path) as picture:
        width, height = picture.size
        if width > 1800:
            new_height = int(height * 1800 / width)
            picture = picture.convert("RGB").resize((1800, new_height))
            small = SHOT_DIR / f".resized_{key}.png"
            picture.save(small, optimize=True)
            path, width, height = small, 1800, new_height
    scale = min(PAGE_WIDTH / width, 380 / height)
    image = Image(str(path), width=width * scale, height=height * scale)
    return KeepTogether([image, Spacer(1, 3), para(label, CAPTION)])


def table(rows: list, widths: list = None, header: bool = True) -> Table:
    """Make a simple grid table with wrapped cells."""
    cells = [[para(str(item), CELL) for item in row] for row in rows]
    result = Table(cells, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")))
    result.setStyle(TableStyle(style))
    return result


def load_json(path: Path):
    """Read a JSON file, or return None when it does not exist."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def block(*items) -> KeepTogether:
    """Keep a code snippet and its screenshot together when they fit."""
    return KeepTogether(list(items))


# ------------------------------------------------------------- sections


def front_matter(args) -> list:
    """Title block, repository link, Section 0 table and setup notes."""
    story = [
        para("DATA 260: Agentic AI", TITLE),
        Spacer(1, 6),
        para("Instructor: Prof. Dr. Simon Shim", SUB),
        para(f"Student Name: {NAME}", SUB),
        para("STUDENT ID: 019124833", SUB),
        para("Homework: 7", SUB),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2f5d8a")),
        Spacer(1, 8),
        Paragraph(
            f'<b>GitHub Repository:</b> <link href="{REPO_URL}" color="blue">'
            f"{REPO_URL}</link>",
            BODY,
        ),
        para("Section 0: Personal Configuration", H1),
        table(
            [
                ["Value", "Setting"],
                ["SID4", "4833"],
                ["PORT_BASE", "8333 (8000 + 4833 mod 900)"],
                ["PREFIX", "s4833"],
                ["SEED", "4833"],
                ["VERIFY_SEED", "264833"],
                ["DOMAIN_ID", "1 (4833 mod 8)"],
                ["Assigned Domain", "Clinical Trial Listings"],
            ],
            [1.6 * inch, PAGE_WIDTH - 1.6 * inch],
        ),
        Spacer(1, 8),
        para(f"**Hardware:** {args.hardware}"),
        para("**Local Model:** qwen3:8b (Ollama); embeddings: nomic-embed-text"),
        para(f"**Tagged commit (tag hw7):** {args.commit}"),
        para("Project Setup", H2),
        para(
            "For Homework 7 I kept working in my existing DATA 260 repository. I "
            "created the hw7-work branch from the final HW6 commit, so the HW6 "
            "submission stays as it was. New code is in the hw7 package, "
            "routers/hw7_auth.py and routers/hw7_trials.py. In main.py I only "
            "added two import lines and two include_router lines, so the HW2 to "
            "HW6 code and routes did not change."
        ),
    ]
    return story


def part1(n: list, missing: list) -> list:
    """Part 1 - JWT authentication, roles and linting."""

    def sh(key: str) -> KeepTogether:
        return shot(key, n, missing)

    story = [para("Part 1 - JWT Authentication, Roles and Linting", H1)]
    story += [
        para("1.1 Users table in MySQL", H2),
        para(
            "The HW4 database already has a users table with different columns "
            "(name, email and a link to sessions). I did not want to change it, so "
            "the HW7 users live in a separate MySQL database, s4833_hw7. The table "
            "has id, a unique username, password_hash and role (reader, writer or "
            "moderator). Passwords are stored only as bcrypt hashes. "
            "init_hw7_db.py creates the table and three demo users, one per role."
        ),
        block(code_function("hw7/db.py", "HW7User"), sh("p1_users_table")),
        para("1.2 Login and /auth/me", H2),
        para(
            "POST /auth/login reads the user from MySQL, checks the password "
            "against the hash and only then creates the token. A wrong password "
            "and an unknown user both return the same 401 message. The token holds "
            "the username, the role and an expiry time (30 minutes). GET /auth/me "
            "returns the id, username and role of the logged-in user."
        ),
        block(code_function("routers/hw7_auth.py", "login"), sh("p1_login")),
        para(
            "The HW7 routes use JWT only. The HW4 session code is unchanged and "
            "no HW7 route uses it."
        ),
        para("get_current_user decodes the token and loads the user from MySQL. "),
        code_function("hw7/deps.py", "get_current_user"),
        block(sh("p1_me_no_token"), sh("p1_me_invalid")),
        para(
            "For the expired-token test I signed a token with the real key and set "
            "its expiry five minutes in the past. It is rejected with 401 and the "
            "message Token has expired."
        ),
        para("1.3 Role-based access on the trial routes", H2),
        para(
            "The domain routes are the clinical-trial routes, now under "
            "/api/hw7/trials. They use the same table and fields as HW5. "
            "require_roles() returns 403 when a valid token has the wrong role."
        ),
        table(
            [
                ["Action", "Route", "Allowed roles"],
                ["List / read", "GET /api/hw7/trials", "reader, writer, moderator"],
                ["Create", "POST /api/hw7/trials", "writer, moderator"],
                ["Delete", "DELETE /api/hw7/trials/{id}", "moderator"],
            ],
            [1.2 * inch, 2.6 * inch, PAGE_WIDTH - 3.8 * inch],
        ),
        Spacer(1, 6),
        code_function("hw7/deps.py", "require_roles"),
        block(
            code_function("routers/hw7_trials.py", "create_trial", 14), sh("p1_create")
        ),
        block(
            code_function("routers/hw7_trials.py", "delete_trial", 14), sh("p1_delete")
        ),
        block(code_function("routers/hw7_trials.py", "list_trials", 14), sh("p1_list")),
        para("1.4 Linting with Ruff and pre-commit", H2),
        para(
            "I added Ruff (rules E, F and I) and a pre-commit hook. The hook only "
            "checks the HW7 files, so older homework code is never reformatted. "
            "In the screenshot I add an unused import and a badly sorted import, "
            "run the commit, and the hook stops it and fixes the files. After "
            "staging the fixed files the commit goes through."
        ),
        block(code_lines(".pre-commit-config.yaml", 1, 10), sh("p1_lint")),
    ]
    return story


def build_story(args) -> tuple:
    """Assemble the finished parts of the report."""
    numbering = [0]
    missing: list = []
    story = front_matter(args)
    story += part1(numbering, missing)
    return story, missing


def main() -> None:
    """Parse arguments, then build the PDF or print the screenshot checklist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="(set after the final commit)")
    parser.add_argument("--hardware", default="Apple MacBook Pro")
    parser.add_argument("--out", default=str(OUT_DIR / "Kulshrestha_HW7.pdf"))
    parser.add_argument("--list-screenshots", action="store_true")
    args = parser.parse_args()

    if args.list_screenshots:
        for key, (caption, how) in SCREENSHOTS.items():
            status = "ok     " if find_shot(key) else "MISSING"
            print(f"[{status}] {key}.png - {caption}\n           {how}")
        return

    story, missing = build_story(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="DATA 260 Homework 7",
        author=NAME,
    ).build(story)
    print(f"wrote {out}")
    print(f"missing screenshots: {len(missing)} {missing}")


if __name__ == "__main__":
    main()
