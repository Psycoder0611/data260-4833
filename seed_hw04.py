import random

from database import db_session_basede26
from models import ClinicalTrialDB, TrialNoteDB


SEED = 4833
PRIMARY_ROWS = 5000
RELATED_ROWS = 200


def seed_data():
    random.seed(SEED)

    db = db_session_basede26()

    try:
        db.query(TrialNoteDB).delete()
        db.query(ClinicalTrialDB).delete()
        db.commit()

        trials = []

        for i in range(1, PRIMARY_ROWS + 1):
            trial = ClinicalTrialDB(
                trialTitle=f"Clinical Trial {i}",
                sponsor=f"Sponsor {((i - 1) % 100) + 1}"
            )
            trials.append(trial)

        db.bulk_save_objects(trials)
        db.commit()

        trial_ids = [
            row[0]
            for row in db.query(ClinicalTrialDB.id).all()
        ]

        notes = []

        for i in range(1, RELATED_ROWS + 1):
            trial_id = random.choice(trial_ids)

            note = TrialNoteDB(
                trial_id=trial_id,
                note=f"Related note {i}"
            )

            notes.append(note)

        db.bulk_save_objects(notes)
        db.commit()

        primary_count = db.query(ClinicalTrialDB).count()
        related_count = db.query(TrialNoteDB).count()

        print(f"Seed: {SEED}")
        print(f"Primary rows: {primary_count}")
        print(f"Related rows: {related_count}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_data()