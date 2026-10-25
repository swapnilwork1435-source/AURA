"""Local scheduler for AURA automations.

Run from the backend directory with: python -m app.automation_worker
The worker stores events in SQLite; browser/OS push delivery is a separate integration.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.main import (
    AutomationPreference, Base, SessionLocal, User, engine, run_automations_for_user,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aura.automation-worker")


def run_once() -> int:
    Base.metadata.create_all(engine)
    processed = 0
    with SessionLocal() as db:
        user_ids = list(db.scalars(select(User.id)))
        for user_id in user_ids:
            try:
                result = run_automations_for_user(user_id, db, datetime.now(timezone.utc))
                processed += 1
                if result["created_events"] or result["new_achievements"]:
                    logger.info("user_id=%s created_events=%s new_achievements=%s",
                                user_id, result["created_events"], len(result["new_achievements"]))
            except Exception:
                db.rollback()
                logger.exception("Automation cycle failed for user_id=%s", user_id)
    return processed


def main() -> None:
    logger.info("AURA automation worker started; polling every 60 seconds.")
    while True:
        run_once()
        time.sleep(60)


if __name__ == "__main__":
    main()
