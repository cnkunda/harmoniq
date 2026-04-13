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

from app.schemas import JobStatus, LessonJSON, LessonSectionStub, PlayerProfile

from app.analyze_audio import build_lesson_json_from_librosa
from app.cache import load_cached_lesson_for_wav, reuse_cached_artifacts_into_job, save_cached_lesson_for_wav
from app.ingest import IngestError, YouTubeUrlInvalidError, get_data_dir, get_job_dir

from app.separate import SeparationError, separate_song_to_stems

logger = logging.getLogger("harmoniq.jobs")
logger.setLevel(logging.INFO)

# In-memory job store (single process).
jobs: dict[str, JobStatus] = {}


def _set_job_processing_progress(job_id: str, progress: float, stage_label: str) -> None:
    """Update progress for an in-flight job; no-op if missing or not processing."""
    current = jobs.get(job_id)
    if current is None or current.status != "processing":
        return
    jobs[job_id] = JobStatus(
        status="processing",
        result=None,
        error=None,
        progress=max(0.0, min(1.0, float(progress))),
        stage_label=stage_label,
    )


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
        transcription_confidence=0.1,
        beat_grid=[0.0, 0.5, 1.0],
        bar_timestamps=[0.0, 3.33, 6.66],
        stems=stems or {},
        lyrics_aligned=[],
        sections=[
            LessonSectionStub(label="Solo (stub)", confidence=0.8, start_time_seconds=0.0),
        ],
        wav_path=wav_path,
    )


def _process_analyze_job(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
    player_profile: PlayerProfile | None = None,
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

        _set_job_processing_progress(job_id, 0.12, "Preparing audio…")
        wav_path_obj = ingest_youtube_or_upload_to_wav(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
        )
        wav_path = str(wav_path_obj)
        _set_job_processing_progress(job_id, 0.28, "Audio ready")
        cached_lesson = load_cached_lesson_for_wav(wav_path_obj, player_profile=player_profile)
        if cached_lesson is not None:
            reused = reuse_cached_artifacts_into_job(cached_lesson, job_id=job_id)
            if reused is not None:
                jobs[job_id] = JobStatus(status="complete", result=reused, error=None)
                logger.info("worker cache hit job_id=%s", job_id)
                return

        job_dir = get_job_dir(job_id)
        _set_job_processing_progress(job_id, 0.4, "Separating stems…")
        stems = separate_song_to_stems(wav_path_obj, job_dir)
        _set_job_processing_progress(job_id, 0.62, "Stems ready")
        guitar_rel_path = stems.get("guitar")
        vocals_rel_path = stems.get("vocals")
        if not guitar_rel_path:
            # Separation contract should always return a guitar stem; fall back to stub.
            result = _stub_lesson(job_id, youtube_url, wav_path=wav_path, stems=stems)
        else:
            _set_job_processing_progress(job_id, 0.78, "Analyzing structure & tabs…")
            backend_root = get_data_dir().parent
            guitar_stem_path = backend_root / guitar_rel_path
            vocals_stem_path = backend_root / vocals_rel_path if vocals_rel_path else None
            result = build_lesson_json_from_librosa(
                job_id,
                guitar_stem_path=guitar_stem_path,
                vocals_stem_path=vocals_stem_path,
                stems=stems,
                wav_path=wav_path,
                source_url=youtube_url,
                player_profile=player_profile,
            )
        save_cached_lesson_for_wav(wav_path_obj, result, player_profile=player_profile)
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
    player_profile: PlayerProfile | None = None,
) -> None:
    """Mark job as processing and start the worker thread."""
    jobs[job_id] = JobStatus(
        status="processing",
        result=None,
        error=None,
        progress=0.05,
        stage_label="Queued…",
    )
    logger.info(
        "enqueue job_id=%s status=processing youtube_url=%r upload_path=%r has_profile=%s",
        job_id,
        youtube_url,
        upload_path,
        player_profile is not None,
    )
    t = threading.Thread(
        target=_process_analyze_job,
        kwargs={
            "job_id": job_id,
            "youtube_url": youtube_url,
            "upload_path": upload_path,
            "player_profile": player_profile,
        },
        daemon=True,
    )
    t.start()

