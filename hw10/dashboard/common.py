# ruff: noqa: E501
"""Cached loaders shared by the pages.

Why two kinds of cache:
  @st.cache_resource  one shared, non-data object for the whole server process: the
                      SpanSource that knows where the log files are. It is created once
                      and never copied or pickled.
  @st.cache_data      results computed from data: parsed spans and result files. Streamlit
                      stores a copy per set of arguments. The file's modification time is
                      an argument, so a changed file gives a fresh load, and ttl=10 s
                      keeps a running experiment visible without reading on every click.
"""

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from hw10 import config, dash_data, tracing


class SpanSource:
    """Knows the log paths; one instance is shared by every session."""

    def __init__(self) -> None:
        """Remember where the files are."""
        self.spans_path = Path(config.SPANS_PATH)
        self.raw_dir = Path(config.RAW_DIR)

    def mtime(self, path: Path) -> float:
        """Modification time (0 if the file does not exist yet)."""
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0


@st.cache_resource
def get_source() -> SpanSource:
    """One SpanSource per server process."""
    return SpanSource()


@st.cache_data(ttl=10, show_spinner=False)
def load_spans(path: str, mtime: float) -> List[Dict[str, Any]]:
    """All spans from the span file (cache key: path + mtime)."""
    return tracing.read_spans(Path(path))


@st.cache_data(ttl=10, show_spinner=False)
def load_json(path: str, mtime: float) -> Any:
    """A JSON result file, or None."""
    return dash_data.read_json(Path(path))


@st.cache_data(ttl=10, show_spinner=False)
def load_jsonl(path: str, mtime: float) -> List[Dict[str, Any]]:
    """A JSON-lines result file."""
    return dash_data.read_jsonl(Path(path))


def spans() -> List[Dict[str, Any]]:
    """Current spans."""
    src = get_source()
    return load_spans(str(src.spans_path), src.mtime(src.spans_path))


def raw_json(name: str) -> Any:
    """A JSON file from reports/hw10/raw/."""
    src = get_source()
    path = src.raw_dir / name
    return load_json(str(path), src.mtime(path))


def raw_jsonl(name: str) -> List[Dict[str, Any]]:
    """A JSON-lines file from reports/hw10/raw/."""
    src = get_source()
    path = src.raw_dir / name
    return load_jsonl(str(path), src.mtime(path))


def source_note(name: str) -> str:
    """Text that names the file behind a metric."""
    return f"Source: reports/hw10/raw/{name}" if name != "spans.jsonl" else f"Source: {config.SPANS_PATH.name} (span log)"
