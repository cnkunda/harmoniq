"""Celery tasks for Harmoniq background job processing.

Wraps the existing _process_analyze_job logic in a Celery task
so jobs are dispatched to a separate worker process.
"""

from __future__ import annotations

import logging
import time

from app.queue import celery_app

logger = logging.getLogger("harmoniq.tasks")


@celery_app.task(
    bind=True,
    name="app.tasks.process_analyze_job",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    track_started=True,
)
def process_analyze_job(
    self,
    job_id: str,
    youtube_url: str | None = None,
    upload_path: str | None = None,
    player_profile: dict | None = None,
    focus_area: str | None = None,
) -> dict:
    """Celery task that runs the full analysis pipeline.

    This wraps the existing _process_analyze_job function, converting
    it from a thread-based model to a Celery task.

    Args:
        job_id: Unique job identifier.
        youtube_url: Optional YouTube URL to analyze.
        upload_path: Optional local file path to analyze.
        player_profile: Optional player profile dict.
        focus_area: Optional coach focus area.

    Returns:
        Dict with job_id and final status.
    """
    from app.job_store import (
        push_to_dlq,
        set_job_complete,
        set_job_failed,
        set_job_processing,
        set_job_progress,
    )

    logger.info(
        "celery_task_start job_id=%s youtube_url=%r upload_path=%r retries=%d",
        job_id,
        youtube_url,
        upload_path,
        self.request.retries,
    )

    set_job_processing(job_id, processing_started_at=time.time())

    try:
        # Deserialize player_profile if provided
        player_profile_obj = None
        if player_profile:
            from app.schemas import PlayerProfile

            try:
                player_profile_obj = PlayerProfile.model_validate(player_profile)
            except Exception:
                logger.warning("invalid player_profile for job_id=%s; ignoring", job_id)

        focus_area_obj = None
        if focus_area:
            from app.schemas import CoachFocusArea

            try:
                focus_area_obj = CoachFocusArea(focus_area)
            except Exception:
                logger.warning("invalid focus_area for job_id=%s; ignoring", job_id)

        # Run the existing pipeline
        from app.jobs import _process_analyze_job

        _process_analyze_job(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
            player_profile=player_profile_obj,
            focus_area=focus_area_obj,
        )

        # Check final status
        from app.job_store import get_job

        final_job = get_job(job_id)
        status = final_job.status if final_job else "unknown"

        logger.info("celery_task_complete job_id=%s status=%s", job_id, status)
        return {"job_id": job_id, "status": status}

    except Exception as exc:
        logger.exception("celery_task_failed job_id=%s exception=%s", job_id, type(exc).__name__)

        # Mark job as failed
        set_job_failed(
            job_id,
            error=str(exc),
            error_code=type(exc).__name__,
        )

        # Push to DLQ if retries exhausted
        if self.request.retries >= self.max_retries:
            push_to_dlq(
                job_id,
                error=str(exc),
                error_code=type(exc).__name__,
                retry_count=self.request.retries,
                job_data={
                    "youtube_url": youtube_url,
                    "upload_path": upload_path,
                },
            )

        # Retry on transient errors
        from app.retry import is_recoverable

        if is_recoverable(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))

        raise
