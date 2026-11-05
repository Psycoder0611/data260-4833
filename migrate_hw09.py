# ruff: noqa: E501
"""Add (or remove) the view_count column that Part 1 persists to.

    python migrate_hw09.py            # add the column (safe to run twice)
    python migrate_hw09.py --remove   # drop it again

Only clinical_trials gets one extra INT column with default 0; models.py and the
HW4 to HW8 code are not touched and keep working.
"""

import sys

from sqlalchemy import inspect, text

from hw9 import config, db
from hw9.logs import banner


def main() -> None:
    """Add or drop the column."""
    print(banner("migrate view_count column"))
    engine = db.make_engine()
    columns = {c["name"] for c in inspect(engine).get_columns(config.TRIALS_TABLE)}
    present = config.VIEWS_COLUMN in columns
    with engine.begin() as conn:
        if "--remove" in sys.argv:
            if present:
                conn.execute(
                    text(
                        f"ALTER TABLE {config.TRIALS_TABLE} DROP COLUMN {config.VIEWS_COLUMN}"
                    )
                )
                print(f"Dropped {config.TRIALS_TABLE}.{config.VIEWS_COLUMN}")
            else:
                print("Column was not there; nothing to do")
        elif present:
            print(f"{config.TRIALS_TABLE}.{config.VIEWS_COLUMN} already exists")
        else:
            conn.execute(
                text(
                    f"ALTER TABLE {config.TRIALS_TABLE} "
                    f"ADD COLUMN {config.VIEWS_COLUMN} INT NOT NULL DEFAULT 0"
                )
            )
            print(f"Added {config.TRIALS_TABLE}.{config.VIEWS_COLUMN} (INT, default 0)")


if __name__ == "__main__":
    main()
