"""Reference cost calculation for the Bay Wheels scenarios (HW7 Part 4).

The agent never uses this. It is an independent check, written in plain Python,
so I can tell whether the agent's numbers and decision are right.
Rates are the ones on the saved pricing page (see the report).
"""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Any, Dict, List

UNLOCK = 1.00  # single ride, per ride
CLASSIC_RATE = 0.19  # single ride, classic, per minute
EBIKE_RATE = 0.49  # single ride, ebike, per minute
MEMBER_FEE = 29.00  # month pass
MEMBER_FREE_MIN = 45  # month pass, classic bikes
MEMBER_RATE = 0.17  # month pass, per minute after free minutes (and on ebikes)

DECISION_MEMBER = "Buy Monthly Membership"
DECISION_PAY = "Pay Per Ride/Minute"


def _minutes(started: str, ended: str) -> float:
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in started else "%Y-%m-%d %H:%M:%S"
    a = datetime.strptime(started, fmt)
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in ended else "%Y-%m-%d %H:%M:%S"
    b = datetime.strptime(ended, fmt)
    return round((b - a).total_seconds() / 60.0, 2)


def rider_rides(csv_path: str, rider_id: str) -> List[Dict[str, Any]]:
    rides = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("synthetic_rider_id") != rider_id:
                continue
            rides.append(
                {
                    "week": datetime.strptime(
                        row["started_at"][:10], "%Y-%m-%d"
                    ).strftime("%W"),
                    "minutes": _minutes(row["started_at"], row["ended_at"]),
                    "ebike": row["rideable_type"].startswith("electric"),
                }
            )
    return rides


def ride_costs(minutes: float, ebike: bool) -> Dict[str, float]:
    pay = UNLOCK + (EBIKE_RATE if ebike else CLASSIC_RATE) * minutes
    extra = MEMBER_RATE * (minutes if ebike else max(minutes - MEMBER_FREE_MIN, 0))
    return {"pay": pay, "member_extra": extra}


def reference(csv_path: str, rider_id: str) -> Dict[str, Any]:
    rides = rider_rides(csv_path, rider_id)
    weeks: Dict[str, Dict[str, float]] = {}
    for r in rides:
        c = ride_costs(r["minutes"], r["ebike"])
        w = weeks.setdefault(
            r["week"], {"rides": 0, "minutes": 0.0, "pay": 0.0, "extra": 0.0}
        )
        w["rides"] += 1
        w["minutes"] += r["minutes"]
        w["pay"] += c["pay"]
        w["extra"] += c["member_extra"]
    pay_total = sum(w["pay"] for w in weeks.values())
    extra_total = sum(w["extra"] for w in weeks.values())
    member_total = MEMBER_FEE + extra_total
    n = len(rides)
    return {
        "rider_id": rider_id,
        "rides": n,
        "pay_total": round(pay_total, 2),
        "member_extra": round(extra_total, 2),
        "member_total": round(member_total, 2),
        "break_even_rides": round(MEMBER_FEE * n / pay_total, 1) if pay_total else None,
        "decision": DECISION_MEMBER if member_total < pay_total else DECISION_PAY,
        "weekly": [
            {
                "week": wk,
                "rides": int(w["rides"]),
                "avg_min": round(w["minutes"] / w["rides"], 1),
                "pay_spend": round(w["pay"], 2),
            }
            for wk, w in sorted(weeks.items())
        ],
    }
