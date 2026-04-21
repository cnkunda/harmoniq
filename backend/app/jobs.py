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

from app.schemas import (
    CoachHydrationSection,
    CoachHydrationStatus,
    JobStatus,
    LessonJSON,
    LessonSectionStub,
    PlayerProfile,
)

from app.analyze_audio import build_lesson_json_from_librosa
from app.cache import load_cached_lesson_for_wav, reuse_cached_artifacts_into_job, save_cached_lesson_for_wav
from app.coach import hydrate_coach_copy_into_sections
from app.ingest import (
    AUDIO_TOO_SHORT_USER_MESSAGE,
    AudioTooShortError,
    IngestError,
    SourceMetadata,
    YouTubeUrlInvalidError,
    get_data_dir,
    get_job_dir,
    resolve_lesson_titles,
)

from app.separate import SeparationError, separate_song_to_stems
from app.stem_quality import classify_stems_for_lesson

logger = logging.getLogger("harmoniq.jobs")
logger.setLevel(logging.INFO)

# Stable `JobStatus.error_code` when status=failed — keep in sync with `mapAnalyzeFlowError` (client).
ANALYZE_ERROR_YOUTUBE_INVALID = "youtube_invalid"
ANALYZE_ERROR_AUDIO_TOO_SHORT = "audio_too_short"
ANALYZE_ERROR_INGEST_FAILED = "ingest_failed"
ANALYZE_ERROR_STEM_SEPARATION_FAILED = "stem_separation_failed"
ANALYZE_ERROR_ANALYSIS_FAILED = "analysis_failed"

# In-memory job store (single process).
jobs: dict[str, JobStatus] = {}
coach_hydration: dict[str, CoachHydrationStatus] = {}


def _set_job_processing_progress(job_id: str, progress: float, stage_label: str) -> None:
    """Update progress for an in-flight job; no-op if missing or not processing."""
    current = jobs.get(job_id)
    if current is None or current.status != "processing":
        return
    started = current.processing_started_at
    if started is None:
        started = time.time()
    jobs[job_id] = JobStatus(
        status="processing",
        result=None,
        error=None,
        progress=max(0.0, min(1.0, float(progress))),
        stage_label=stage_label,
        processing_started_at=float(started),
    )


def _lesson_with_skeleton_coach(lesson: LessonJSON) -> LessonJSON:
    sections: list[LessonSectionStub] = []
    for sec in lesson.sections:
        payload = sec.model_dump(exclude_none=True)
        payload["coach_note"] = ""
        payload["coach_explanation"] = ""
        sections.append(LessonSectionStub(**payload))
    return lesson.model_copy(update={"sections": sections})


def _set_coach_pending(job_id: str, section_count: int) -> None:
    coach_hydration[job_id] = CoachHydrationStatus(
        status="pending",
        sections=[CoachHydrationSection(index=i, coach_note="", coach_explanation="") for i in range(max(0, section_count))],
        fallback_reason=None,
    )


def _lesson_has_hydrated_coach(lesson: LessonJSON) -> bool:
    for sec in lesson.sections:
        payload = sec.model_dump(exclude_none=True)
        note = payload.get("coach_note")
        explanation = payload.get("coach_explanation")
        if isinstance(note, str) and note.strip() and isinstance(explanation, str) and explanation.strip():
            return True
    return False


def _hydrate_coach_copy_job(
    job_id: str,
    *,
    player_profile: PlayerProfile | None,
) -> None:
    job = jobs.get(job_id)
    if job is None or job.result is None:
        return
    lesson = job.result
    sections = [LessonSectionStub(**s.model_dump(exclude_none=True)) for s in lesson.sections]
    enriched, status, fallback_reason = hydrate_coach_copy_into_sections(
        sections,
        song_title=lesson.song_title,
        artist=lesson.artist,
        key=lesson.key,
        player_profile=player_profile,
        style_label=lesson.style_label,
        technique_hints=[],
    )
    patched = lesson.model_copy(update={"sections": enriched})
    jobs[job_id] = JobStatus(status="complete", result=patched, error=None)
    coach_hydration[job_id] = CoachHydrationStatus(
        status=status,
        sections=[
            CoachHydrationSection(
                index=i,
                coach_note=str(getattr(sec, "coach_note", "") or ""),
                coach_explanation=str(getattr(sec, "coach_explanation", "") or ""),
            )
            for i, sec in enumerate(enriched)
        ],
        fallback_reason=fallback_reason,
    )
    logger.info("coach_hydration complete job_id=%s status=%s fallback_reason=%s", job_id, status, fallback_reason)


def get_coach_hydration(job_id: str) -> CoachHydrationStatus | None:
    return coach_hydration.get(job_id)


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
    source_metadata: SourceMetadata | None = None,
) -> LessonJSON:
    """Deterministic fake lesson for client contract tests; pipeline replaces this later."""
    song_title, artist = resolve_lesson_titles(source_metadata, source_url=source_url)

    # Note: LessonJSON allows extra fields (extra="allow"), so `wav_path` can be
    # carried forward without changing the public schema yet.
    # No librosa pass here — match HARMONIQ_SKIP_STYLE_DETECT placeholder (D2 contract).
    return LessonJSON(
        job_id=job_id,
        song_title=song_title,
        artist=artist,
        style_label="general",
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
        wav_path_obj, source_metadata = ingest_youtube_or_upload_to_wav(
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
                if _lesson_has_hydrated_coach(reused):
                    coach_hydration[job_id] = CoachHydrationStatus(
                        status="complete",
                        sections=[
                            CoachHydrationSection(
                                index=i,
                                coach_note=str((sec.model_dump(exclude_none=True).get("coach_note") or "")),
                                coach_explanation=str((sec.model_dump(exclude_none=True).get("coach_explanation") or "")),
                            )
                            for i, sec in enumerate(reused.sections)
                        ],
                        fallback_reason=None,
                    )
                else:
                    _set_coach_pending(job_id, len(reused.sections))
                    coach_thread = threading.Thread(
                        target=_hydrate_coach_copy_job,
                        kwargs={"job_id": job_id, "player_profile": player_profile},
                        daemon=True,
                    )
                    coach_thread.start()
                logger.info("worker cache hit job_id=%s", job_id)
                return

        job_dir = get_job_dir(job_id)
        _set_job_processing_progress(job_id, 0.4, "Separating stems…")
        stems = separate_song_to_stems(wav_path_obj, job_dir)
        _set_job_processing_progress(job_id, 0.62, "Stems ready")
        backend_root = get_data_dir().parent
        stem_abs_paths = {k: backend_root / rel for k, rel in stems.items()}
        stem_classification = classify_stems_for_lesson(wav_path_obj, stem_abs_paths)
        if stem_classification.flags:
            logger.info(
                "stem_quality job_id=%s flags=%s usable=%s role=%s",
                job_id,
                ",".join(stem_classification.flags),
                stem_classification.guitar_stem_usable,
                stem_classification.analysis_audio_role,
            )
        guitar_rel_path = stems.get("guitar")
        vocals_rel_path = stems.get("vocals")
        if not guitar_rel_path:
            # Separation contract should always return a guitar stem; fall back to stub.
            stub = _stub_lesson(
                job_id,
                youtube_url,
                wav_path=wav_path,
                stems=stems,
                source_metadata=source_metadata,
            )
            result = stub
        else:
            _set_job_processing_progress(job_id, 0.78, "Analyzing structure & tabs…")
            guitar_stem_path = backend_root / guitar_rel_path
            vocals_stem_path = backend_root / vocals_rel_path if vocals_rel_path else None
            piano_rel = stems.get("piano")
            piano_stem_path = (backend_root / piano_rel) if piano_rel else None
            result = build_lesson_json_from_librosa(
                job_id,
                guitar_stem_path=guitar_stem_path,
                vocals_stem_path=vocals_stem_path,
                stems=stems,
                wav_path=wav_path,
                source_url=youtube_url,
                player_profile=player_profile,
                source_metadata=source_metadata,
                stem_classification=stem_classification,
                mix_wav_path=wav_path_obj,
                piano_stem_path=piano_stem_path,
            )
        skeleton_result = _lesson_with_skeleton_coach(result)
        save_cached_lesson_for_wav(wav_path_obj, skeleton_result, player_profile=player_profile)
        jobs[job_id] = JobStatus(status="complete", result=skeleton_result, error=None)
        _set_coach_pending(job_id, len(skeleton_result.sections))
        coach_thread = threading.Thread(
            target=_hydrate_coach_copy_job,
            kwargs={"job_id": job_id, "player_profile": player_profile},
            daemon=True,
        )
        coach_thread.start()
        logger.info("worker complete job_id=%s", job_id)
    except YouTubeUrlInvalidError:
        logger.warning("worker failed job_id=%s invalid youtube_url", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=YOUTUBE_URL_INVALID_USER_MESSAGE,
            error_code=ANALYZE_ERROR_YOUTUBE_INVALID,
        )
    except AudioTooShortError:
        logger.warning("worker failed job_id=%s audio too short", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=AUDIO_TOO_SHORT_USER_MESSAGE,
            error_code=ANALYZE_ERROR_AUDIO_TOO_SHORT,
        )
    except IngestError:
        logger.exception("worker failed job_id=%s ingest error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_INGEST_FAILED,
        )
    except SeparationError:
        logger.exception("worker failed job_id=%s stem separation error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=STEM_SEPARATION_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_STEM_SEPARATION_FAILED,
        )
    except Exception:
        # Fail loudly in logs; user sees a warm, safe message.
        logger.exception("worker failed job_id=%s", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_ANALYSIS_FAILED,
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
        processing_started_at=time.time(),
    )
    coach_hydration[job_id] = CoachHydrationStatus(status="pending", sections=[], fallback_reason=None)
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

