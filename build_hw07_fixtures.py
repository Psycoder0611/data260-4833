"""Build the hostile pricing page for HW7 Part 5 and check it ranks.

python -u build_hw07_fixtures.py
"""

import hashlib
from pathlib import Path

from hw7 import bike_security, bike_tools

FIX = Path("reports/hw07/fixtures")
QUERY = "single ride month pass price unlock free minutes per-minute classic ebike"


def main() -> None:
    clean = (FIX / "bike_pricing_clean.txt").read_text(encoding="utf-8")
    hostile = bike_security.build_hostile_text(clean)
    out = FIX / "bike_pricing_hostile.txt"
    out.write_text(hostile, encoding="utf-8")
    print(f"wrote {out} ({len(hostile.splitlines())} lines)")
    print(f"sha256 {hashlib.sha256(hostile.strip().encode()).hexdigest()}")
    page = {"text": hostile.strip()}
    res = bike_tools.policy_retriever("x", QUERY, 10, lambda _u: page)
    top = [p["text"] for p in res["data"]["passages"]]
    for name, line in bike_security.INJECTIONS.items():
        rank = top.index(line) + 1 if line in top else None
        print(f"{name:9} {len(line)} chars  rank in top 10: {rank}")


if __name__ == "__main__":
    main()
