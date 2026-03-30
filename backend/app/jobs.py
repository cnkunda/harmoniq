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

from app.ingest import IngestError, YouTubeUrlInvalidError, get_job_dir

from app.separate import SeparationError, separate_song_to_stems

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

# Must match README.md "YouTube URL invalid" message.
YOUTUBE_URL_INVALID_USER_MESSAGE = (
    "That URL didn't work — make sure it's a full YouTube link and try again."
)

# Keep short so the acceptance criteria ("within a few seconds") is satisfied.
PROCESSING_SLEEP_SECONDS = 0.1

# Must be user-safe and actionable on separation failures.
STEM_SEPARATION_FAILED_USER_MESSAGE = (
    "Something went wrong separating guitar stems. Try a studio recording — live versions "
    "sometimes have unusual audio."
)


def _stub_lesson(
    job_id: str,
    source_url: str | None,
    *,
    wav_path: str | None = None,
    stems: dict[str, str] | None = None,
) -> LessonJSON:
    """Deterministic fake lesson for client contract tests; pipeline replaces this later."""
    _ = source_url  # reserved for future ingest logging

    # Note: LessonJSON allows extra fields (extra="allow"), so `wav_path` can be
    # carried forward without changing the public schema yet.
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
        stems=stems or {},
        lyrics_aligned=[],
        sections=[
            LessonSectionStub(label="Solo (stub)", confidence=0.8),
        ],
        wav_path=wav_path,
    )


def _process_analyze_job(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
) -> None:
    """Worker loop for one analyze job.

    Thread-based on purpose: FastAPI `TestClient` polling can otherwise block
    asyncio task progress, causing jobs to remain stuck in `processing`.
    """
    logger.info("worker start job_id=%s youtube_url=%r upload_path=%r", job_id, youtube_url, upload_path)
    time.sleep(PROCESSING_SLEEP_SECONDS)

    try:
        if youtube_url == FORCED_EXCEPTION_INPUT:
            # Smoke-test hook for PRIORITIES §4 acceptance criteria.
            raise RuntimeError("Forced exception from request payload")

        from app.ingest import ingest_youtube_or_upload_to_wav

        wav_path_obj = ingest_youtube_or_upload_to_wav(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
        )
        wav_path = str(wav_path_obj)

        job_dir = get_job_dir(job_id)
        stems = separate_song_to_stems(wav_path_obj, job_dir)
        result = _stub_lesson(job_id, youtube_url, wav_path=wav_path, stems=stems)
        jobs[job_id] = JobStatus(status="complete", result=result, error=None)
        logger.info("worker complete job_id=%s", job_id)
    except YouTubeUrlInvalidError:
        logger.warning("worker failed job_id=%s invalid youtube_url", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=YOUTUBE_URL_INVALID_USER_MESSAGE,
        )
    except IngestError:
        logger.exception("worker failed job_id=%s ingest error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
        )
    except SeparationError:
        logger.exception("worker failed job_id=%s stem separation error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=STEM_SEPARATION_FAILED_USER_MESSAGE,
        )
    except Exception:
        # Fail loudly in logs; user sees a warm, safe message.
        logger.exception("worker failed job_id=%s", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
        )


def enqueue_analyze_job(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
) -> None:
    """Mark job as processing and start the worker thread."""
    jobs[job_id] = JobStatus(status="processing", result=None, error=None)
    logger.info("enqueue job_id=%s status=processing youtube_url=%r upload_path=%r", job_id, youtube_url, upload_path)
    t = threading.Thread(
        target=_process_analyze_job,
        kwargs={"job_id": job_id, "youtube_url": youtube_url, "upload_path": upload_path},
        daemon=True,
    )
    t.start()

