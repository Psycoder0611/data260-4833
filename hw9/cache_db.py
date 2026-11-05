"""Database + Redis class for Part 1 (the view counter).

ClinicalTrialCache holds the MySQL engine and a Redis client. Part 1 adds exactly
one method to it: increment_clinical_trial_views().
"""

import logging
from typing import Optional

from sqlalchemy.engine import Engine

from hw9 import config, db
from hw9.logs import get_logger


class ClinicalTrialCache:
    """Clinical trial access with Redis in front of the database."""

    def __init__(
        self,
        redis_client,
        engine: Optional[Engine] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Keep the Redis client and the database engine."""
        self.redis_client = redis_client
        self.engine = engine or db.make_engine()
        self.log = logger or get_logger("VIEWS")

    def views_key(self, trial_id: int) -> str:
        """Redis key of the counter, e.g. s4833:views:clinical_trial:1."""
        return config.VIEWS_KEY_FORMAT.format(id=trial_id)

    def increment_clinical_trial_views(self, trial_id: int) -> int:
        """Count one access of a trial and return the current total.

        1. INCR the Redis counter (atomic, no database read).
        2. Every 10th increment, write the count to the trial's database row.
        3. Return the count.
        """
        key = self.views_key(trial_id)
        count = int(self.redis_client.incr(key))
        if count % config.SYNC_EVERY == 0:
            db.set_view_count(self.engine, trial_id, count)
            self.log.info(
                "Synced views to database (trial %s, count %s)", trial_id, count
            )
        return count
