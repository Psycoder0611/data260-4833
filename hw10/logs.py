"""Banner, console logger and RUN_LOG tee for HW10 scripts."""

import contextlib
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from hw8.logs import _Tee, get_logger  # noqa: F401  (same line format as HW8/HW9)

from hw10 import config


def banner(title: str) -> str:
    """Identification line printed at the top of every run."""
    return (
        f"Student: {config.STUDENT_NAME} | SID4 {config.SID4} | "
        f"HW{config.HOMEWORK} {title}"
    )


@contextlib.contextmanager
def run_logged(title: str, path: Optional[Path] = None) -> Iterator[None]:
    """Copy everything printed inside the block to RUN_LOG.txt (append mode)."""
    log_path = path or config.RUN_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    original = sys.stdout
    with open(log_path, "a", encoding="utf-8") as handle:
        stamp = time.strftime("%a %b %d %H:%M:%S %Z %Y")
        handle.write(f"===== HW10 {title.upper()} RUN START: {stamp} =====\n")
        sys.stdout = _Tee(original, handle)  # type: ignore[assignment]
        try:
            print(banner(title))
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            yield
        finally:
            sys.stdout = original
            stamp = time.strftime("%a %b %d %H:%M:%S %Z %Y")
            handle.write(f"===== HW10 {title.upper()} RUN END: {stamp} =====\n")
