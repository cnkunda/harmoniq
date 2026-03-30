"""In-memory background jobs for analysis.

This implements PRIORITIES §4:
* POST /analyze returns a job_id immediately
* a worker transitions job status:
  processing -> complete | failed
* failed jobs store a user-safe error string

Scope note: single-process in-memory store is intentional for v1.
"""

from __future__ import annotations

import logging
import threading
import time

from app.schemas import JobStatus, LessonJSON, LessonSectionStub

logger = logging.getLogger("harmoniq.jobs")
logger.setLevel(logging.INFO)

# In-memory job store (single process).
jobs: dict[str, JobStatus] = {}


# Used by tests / smoke forcing.
FORCED_EXCEPTION_INPUT = "force_error"

# Must match README.md "Analysis job failed" message.
ANALYSIS_FAILED_USER_MESSAGE = (
    "Something went wrong processing that song. Try a studio recording — "
    "live versions sometimes have unusual audio."
)

# Keep short so the acceptance criteria ("within a few seconds") is satisfied.
PROCESSING_SLEEP_SECONDS = 1.0


def _stub_lesson(job_id: str, source_url: str | None) -> LessonJSON:
    """Deterministic fake lesson for client contract tests; pipeline replaces this later."""
    _ = source_url  # reserved for future ingest logging
    return LessonJSON(
        job_id=job_id,
        song_title="Stub Song",
        artist="Stub Artist",
        key="G major",
        key_confidence=0.99,
        tempo=72.0,
        tempo_confidence=0.95,
        transcription_confidence=0.5,
        beat_grid=[0.0, 0.5, 1.0],
        bar_timestamps=[0.0, 3.33, 6.66],
        stems={},
        lyrics_aligned=[],
        sections=[
            LessonSectionStub(label="Solo (stub)", confidence=0.8),
        ],
    )


def _process_analyze_job(job_id: str, url: str | None) -> None:
    """Worker loop for one analyze job.

    Thread-based on purpose: FastAPI `TestClient` polling can otherwise block
    asyncio task progress, causing jobs to remain stuck in `processing`.
    """
    logger.info("worker start job_id=%s url=%r", job_id, url)
    time.sleep(PROCESSING_SLEEP_SECONDS)

    try:
        if url == FORCED_EXCEPTION_INPUT:
            # Smoke-test hook for PRIORITIES §4 acceptance criteria.
            raise RuntimeError("Forced exception from request payload")

        result = _stub_lesson(job_id, url)
        jobs[job_id] = JobStatus(status="complete", result=result, error=None)
        logger.info("worker complete job_id=%s", job_id)
    except Exception:
        # Fail loudly in logs; user sees a warm, safe message.
        logger.exception("worker failed job_id=%s", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
        )


def enqueue_analyze_job(job_id: str, url: str | None) -> None:
    """Mark job as processing and start the worker thread."""
    jobs[job_id] = JobStatus(status="processing", result=None, error=None)
    logger.info("enqueue job_id=%s status=processing url=%r", job_id, url)
    t = threading.Thread(
        target=_process_analyze_job,
        args=(job_id, url),
        daemon=True,
    )
    t.start()

