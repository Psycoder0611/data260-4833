"""Six file tools and a bash safety gate (HW7 Part 6).

Every file tool works only inside one sandbox directory. The safety gate
(is_destructive, confirm_bash) is plain Python and needs no model.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from hw7.bike_tools import envelope

SANDBOX: Optional[Path] = None
MAX_LINES = 200  # read_file default
MAX_HITS = 50  # search_in_files, glob_files
OUTPUT_CHARS = 1500  # bash output kept
BASH_TIMEOUT_S = 10


def make_sandbox() -> Path:
    """A fresh temporary course sandbox; all tests happen inside it."""
    return set_sandbox(Path(tempfile.mkdtemp(prefix="course_sandbox_")))


def set_sandbox(path: Path) -> Path:
    global SANDBOX
    SANDBOX = Path(path).resolve()
    return SANDBOX


def _resolve(path: str) -> Path:
    if SANDBOX is None:
        raise ValueError("no sandbox is set")
    full = (SANDBOX / path).resolve()
    if full != SANDBOX and SANDBOX not in full.parents:
        raise ValueError(f"path is outside the sandbox: {path}")
    return full


def _rel(full: Path) -> str:
    return str(full.relative_to(SANDBOX))


# --------------------------------------------------------------------------
# The six tools
# --------------------------------------------------------------------------


def read_file(path: str, max_lines: int = MAX_LINES) -> Dict[str, Any]:
    try:
        lines = _resolve(path).read_text(encoding="utf-8").splitlines()
    except (ValueError, OSError) as exc:
        return envelope(False, error=str(exc))
    shown = lines[: max(1, int(max_lines))]
    data = {
        "path": path,
        "text": "\n".join(shown),
        "lines_shown": len(shown),
        "total_lines": len(lines),
        "truncated": len(shown) < len(lines),
    }
    return envelope(True, data)


def write_file(path: str, content: str) -> Dict[str, Any]:
    try:
        full = _resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    except (ValueError, OSError) as exc:
        return envelope(False, error=str(exc))
    return envelope(True, {"path": path, "chars_written": len(content)})


def edit_file(path: str, old: str, new: str) -> Dict[str, Any]:
    try:
        full = _resolve(path)
        before = full.read_text(encoding="utf-8")
    except (ValueError, OSError) as exc:
        return envelope(False, error=str(exc))
    count = before.count(old) if old else 0
    if count != 1:
        return envelope(False, error=f"'old' must appear exactly once (found {count})")
    after = before.replace(old, new, 1)
    full.write_text(after, encoding="utf-8")
    diff = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(), path, path, lineterm="", n=1
        )
    )
    return envelope(True, {"path": path, "diff": "\n".join(diff[:20])})


def glob_files(pattern: str) -> Dict[str, Any]:
    if SANDBOX is None:
        return envelope(False, error="no sandbox is set")
    try:
        found = sorted(_rel(p) for p in SANDBOX.glob(pattern) if p.is_file())
    except (ValueError, NotImplementedError) as exc:
        return envelope(False, error=f"bad pattern: {exc}")
    return envelope(True, {"files": found[:MAX_HITS], "count": len(found)})


def search_in_files(pattern: str, file_pattern: str = "*") -> Dict[str, Any]:
    if SANDBOX is None:
        return envelope(False, error="no sandbox is set")
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return envelope(False, error=f"bad regex: {exc}")
    hits: List[Dict[str, Any]] = []
    for file in sorted(SANDBOX.rglob(file_pattern)):
        if not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            if regex.search(line):
                hits.append({"file": _rel(file), "line": number, "text": line[:200]})
    return envelope(True, {"matches": hits[:MAX_HITS], "count": len(hits)})


def bash(command: str, auto_approve: bool = False) -> Dict[str, Any]:
    gate = confirm_bash(command, auto_approve)
    if not gate["allow"]:
        return envelope(False, error=f"blocked: {gate['reason']}")
    if SANDBOX is None:
        return envelope(False, error="no sandbox is set")
    try:
        done = subprocess.run(
            command, shell=True, cwd=SANDBOX, capture_output=True, text=True,
            timeout=BASH_TIMEOUT_S,
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return envelope(False, error=f"timed out after {BASH_TIMEOUT_S} s")
    out = (done.stdout + done.stderr)[:OUTPUT_CHARS]
    return envelope(True, {"exit_code": done.returncode, "output": out})


# --------------------------------------------------------------------------
# The safety gate
# --------------------------------------------------------------------------

# A command is on the allow-list when every part of it (split on | ; && & newline)
# starts with one of these words.
SAFE_PREFIXES = (
    "ls", "pwd", "cat", "head", "tail", "wc", "echo", "grep", "find",
    "date", "whoami", "git status", "git diff", "git log",
    "python --version", "python3 --version",
)  # fmt: skip

# Independent deny-list. Each pattern is one of the six required categories.
DESTRUCTIVE_PATTERNS = {
    "recursive deletion": [
        r"\brm\b[^|;&]*\s-[a-zA-Z]*[rR]",
        r"\brm\b[^|;&]*--recursive",
        r"\bfind\b[^|;&]*-delete\b",
        r"\brmtree\b",
    ],
    "privilege escalation": [r"\b(sudo|su|doas|pkexec)\b"],
    "permission or ownership change": [r"\b(chmod|chown|chgrp|setfacl)\b"],
    "raw device write": [
        r"\bdd\b[^|;&]*\bof=/dev/",
        r">>?\s*/dev/(sd|hd|nvme|disk|rdisk|mmcblk)",
    ],
    "filesystem creation": [
        r"\b(mkfs(\.\w+)?|mke2fs|mkswap|newfs\w*)\b",
        r"\bdiskutil\s+(erase|partition|reformat)",
    ],  # fmt: skip
    "redirection to a root path": [r">>?\s*/(?!dev/null\b)"],
}


def _destructive_reason(command: str) -> Optional[str]:
    for reason, patterns in DESTRUCTIVE_PATTERNS.items():
        if any(re.search(p, command) for p in patterns):
            return reason
    return None


def is_destructive(command: str) -> bool:
    """True if the command matches the deny-list. Independent of SAFE_PREFIXES."""
    return _destructive_reason(command or "") is not None


def _is_safe(command: str) -> bool:
    if re.search(r"`|\$\(|<\(|>", command):  # substitution or redirection
        return False
    if re.search(r"\bfind\b[^|;&]*\s-(exec|execdir|ok)\b", command):
        return False  # find can run any other command
    parts = [p.strip() for p in re.split(r"\|\||&&|;|\||&|\n", command)]
    return all(
        p and any(p == s or p.startswith(s + " ") for s in SAFE_PREFIXES) for p in parts
    )


def confirm_bash(command: str, auto_approve: bool = False) -> Dict[str, Any]:
    """Allow or block a bash command. auto_approve=True is the explicit confirmation."""
    command = (command or "").strip()
    if not command:
        return {"allow": False, "reason": "empty command"}
    reason = _destructive_reason(command)
    if reason:
        if auto_approve:
            return {"allow": True, "reason": f"destructive ({reason}), confirmed"}
        return {"allow": False, "reason": f"destructive ({reason})"}
    if _is_safe(command):
        return {"allow": True, "reason": "matches SAFE_PREFIXES"}
    if auto_approve:
        return {"allow": True, "reason": "not on the allow-list, confirmed"}
    return {"allow": False, "reason": "not on the allow-list"}


TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "glob_files": glob_files,
    "search_in_files": search_in_files,
    "bash": bash,
}
