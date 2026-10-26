"""Add (or remove) five labeled HW7 sample trials for the Part 2 agent tasks.

The HW5 table only has one searchable trial, so the multi-step tasks need a few
more. These rows use codes CT-2026-101 to CT-2026-105 and belong to the existing
organization 2. Nothing else in the table is touched.

    python seed_hw07_trials.py            # add (safe to run twice)
    python seed_hw07_trials.py --remove   # delete only these five rows
"""

import sys

from database import db_session_basede26
from models import ClinicalTrialDB, ResearchOrganizationDB

ORGANIZATION_ID = 2
SPONSOR = "Stanford Clinical Trials Center"  # sponsor column is required
SAMPLE_TRIALS = [
    ("CT-2026-101", "Cardiac Rehabilitation Outcomes Trial", 80),
    ("CT-2026-102", "Diabetes Prevention Lifestyle Study", 200),
    ("CT-2026-103", "Oncology Immunotherapy Phase II", 60),
    ("CT-2026-104", "Pediatric Asthma Inhaler Comparison", 150),
    ("CT-2026-105", "Hypertension Medication Adherence Study", 90),
]


def main() -> None:
    remove = "--remove" in sys.argv
    print("Trapti Kulshrestha | SID4 4833 | HW7 sample trials")
    db = db_session_basede26()
    try:
        codes = [code for code, _, _ in SAMPLE_TRIALS]
        if remove:
            rows = (
                db.query(ClinicalTrialDB)
                .filter(ClinicalTrialDB.trial_code.in_(codes))
                .all()
            )
            for row in rows:
                db.delete(row)
            db.commit()
            print(f"Removed {len(rows)} sample trials")
            return
        if db.get(ResearchOrganizationDB, ORGANIZATION_ID) is None:
            print(f"Organization {ORGANIZATION_ID} not found; nothing added")
            return
        added = 0
        for code, title, capacity in SAMPLE_TRIALS:
            exists = (
                db.query(ClinicalTrialDB)
                .filter(ClinicalTrialDB.trial_code == code)
                .first()
            )
            if exists:
                continue
            db.add(
                ClinicalTrialDB(
                    trialTitle=title,
                    sponsor=SPONSOR,
                    trial_code=code,
                    participant_capacity=capacity,
                    organization_id=ORGANIZATION_ID,
                )
            )
            added += 1
        db.commit()
        print(f"Added {added} sample trials (already present: {len(codes) - added})")
        searchable = (
            db.query(ClinicalTrialDB)
            .filter(ClinicalTrialDB.trial_code.isnot(None))
            .order_by(ClinicalTrialDB.id)
            .all()
        )
        for trial in searchable:
            print(
                trial.id,
                trial.trial_code,
                trial.trialTitle,
                trial.participant_capacity,
                trial.organization_id,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
