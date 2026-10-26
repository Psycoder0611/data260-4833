"""HW7 Part 4: save one pricing-page snapshot (text, URL, access time, SHA-256).

python run_hw07_snapshot.py --url https://lyftbikes.com/pricing --out NAME
Writes reports/hw07/raw/pricing_snapshot_NAME.txt and .json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hw7 import bike_policy
from hw7.config import RAW_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://lyftbikes.com/pricing")
    ap.add_argument("--out", default="preview")
    ap.add_argument("--show", action="store_true", help="print the text")
    args = ap.parse_args()

    page = bike_policy.fetch_page(args.url)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    txt = Path(RAW_DIR) / f"pricing_snapshot_{args.out}.txt"
    meta = Path(RAW_DIR) / f"pricing_snapshot_{args.out}.json"
    txt.write_text(page["text"] + "\n", encoding="utf-8")
    meta.write_text(
        json.dumps(
            {k: page[k] for k in ("url", "access_ts", "sha256")}
            | {"chars": len(page["text"]), "lines": page["text"].count("\n") + 1},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.show:
        print(page["text"])
        print("-" * 60)
    print(f"url:     {page['url']}")
    print(f"access:  {page['access_ts']} (UTC)")
    print(f"sha256:  {page['sha256']}")
    print(f"saved:   {txt.relative_to(txt.parents[3])}")


if __name__ == "__main__":
    main()
