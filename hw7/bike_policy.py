"""Fetching and reading the public pricing page (HW7 Part 4)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (HW7 student project; DATA 260)"
TIMEOUT_S = 20


def extract_text(html: str) -> str:
    """Visible text of a page, one block per line, no scripts or styles."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def fetch_page(url: str) -> Dict[str, str]:
    """Download a page. file:// paths are read from disk (used for fixtures)."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if url.startswith("file://"):
        with open(url[len("file://") :], "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        resp.raise_for_status()
        raw = resp.text
    text = extract_text(raw) if "<" in raw[:2000] else raw.strip()
    return {
        "url": url,
        "access_ts": ts,
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def split_lines(text: str) -> List[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
