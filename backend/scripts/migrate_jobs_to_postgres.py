"""One-time migration: load legacy disk-persisted jobs into Postgres.

Run this after deploying the database schema to migrate any existing
JobStatus.json files from the data/jobs/ directory into the jobs table.

Usage:
    python scripts/migrate_jobs_to_postgres.py

Safe to re-run — skips already-migrated jobs.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")


def main() -> None:
    # Initialize DB
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db import init_db, get_session
    from app.models import Base, JobModel, CoachHydrationModel, ChordEnrichmentModel
    from sqlalchemy import inspect

    init_db()
    session = get_session()

    # Ensure tables exist
    inspector = inspect(session.bind)
    existing = inspector.get_table_names()
    if "jobs" not in existing:
        logger.error("Jobs table does not exist. Run `alembic upgrade head` first.")
        session.close()
        sys.exit(1)

    data_dir = Path(__file__).resolve().parents[1] / "data"
    jobs_dir = data_dir / "jobs"

    if not jobs_dir.exists():
        logger.info("No legacy jobs directory found at %s", jobs_dir)
        session.close()
        return

    migrated = 0
    skipped = 0

    for job_dir in sorted(jobs_dir.iterdir()):
        if not job_dir.is_dir():
            continue
        status_file = job_dir / "JobStatus.json"
        if not status_file.exists():
            continue

        job_id = job_dir.name

        # Skip if already in DB
        from sqlalchemy import select
        existing_job = session.execute(
            select(JobModel).where(JobModel.job_id == job_id)
        ).scalar_one_or_none()
        if existing_job is not None:
            skipped += 1
            continue

        try:
            raw = json.loads(status_file.read_text(encoding="utf-8"))
            status = raw.get("status", "failed")

            # Also load coach hydration if available
            coach_file = job_dir / "CoachHydration.json"
            if coach_file.exists():
                try:
                    coach_raw = json.loads(coach_file.read_text(encoding="utf-8"))
                    session.add(
                        CoachHydrationModel(
                            job_id=job_id,
                            status=coach_raw.get("status", "pending"),
                            sections=coach_raw.get("sections", []),
                            fallback_reason=coach_raw.get("fallback_reason"),
                        )
                    )
                except Exception:
                    logger.warning("Failed to migrate coach hydration for %s", job_id)

            session.add(
                JobModel(
                    job_id=job_id,
                    status=status,
                    progress=raw.get("progress"),
                    stage_label=raw.get("stage_label"),
                    analysis_stage=raw.get("analysis_stage"),
                    error=raw.get("error"),
                    error_code=raw.get("error_code"),
                    processing_started_at=raw.get("processing_started_at"),
                    result=raw.get("result"),
                )
            )
            session.commit()
            migrated += 1
            logger.info("Migrated job %s (status=%s)", job_id, status)
        except Exception:
            session.rollback()
            logger.exception("Failed to migrate job %s", job_id)

    session.close()
    logger.info("Migration complete: %d migrated, %d skipped", migrated, skipped)


if __name__ == "__main__":
    main()
