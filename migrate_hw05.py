from sqlalchemy import inspect, text

from database import engine
from models import Base


def migrate_hw05():
    # Creates any completely new tables,
    # including research_organizations.
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)

    columns = {
        column["name"]
        for column in inspector.get_columns("clinical_trials")
    }

    with engine.begin() as connection:

        if "trial_code" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD COLUMN trial_code VARCHAR(100) NULL UNIQUE
                    """
                )
            )
            print("Added trial_code")

        if "participant_capacity" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD COLUMN participant_capacity INT
                    NOT NULL DEFAULT 100
                    """
                )
            )
            print("Added participant_capacity")

        if "organization_id" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD COLUMN organization_id INT NULL
                    """
                )
            )

            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD CONSTRAINT fk_trials_organization
                    FOREIGN KEY (organization_id)
                    REFERENCES research_organizations(id)
                    ON DELETE RESTRICT
                    """
                )
            )

            print("Added organization_id")

        if "created_at" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD COLUMN created_at DATETIME
                    NOT NULL DEFAULT CURRENT_TIMESTAMP
                    """
                )
            )
            print("Added created_at")

        if "updated_at" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE clinical_trials
                    ADD COLUMN updated_at DATETIME
                    NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    """
                )
            )
            print("Added updated_at")

    print("HW5 migration completed successfully.")


if __name__ == "__main__":
    migrate_hw05()