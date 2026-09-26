"""Celery tasks for the Harmoniq analysis pipeline.

These tasks replace the threading.Thread workers in app.jobs.
Each task runs in a Celery worker process and communicates progress
through the Postgres repository + Redis pub/sub for WebSocket clients.
"""

from __future__ import annotations

import logging
import os
import time

from app.celery_app import app

logger = logging.getLogger("harmoniq.tasks")


def _publish_progress(job_id: str, status: str, **payload) -> None:
    """Publish job progress to Redis pub/sub for WebSocket relay."""
    try:
        import json as _json
        import redis as _redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = _redis.from_url(redis_url)
        msg = _json.dumps({"type": "status", "status": status, **payload})
        r.publish(f"job:{job_id}:progress", msg)
        r.close()
    except Exception:
        logger.debug("Failed to publish progress for job_id=%s (non-fatal)", job_id)


@app.task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def analyze_job_task(
    self,
    job_id: str,
    youtube_url: str | None = None,
    upload_path: str | None = None,
    player_profile: dict | None = None,
    focus_area: str | None = None,
) -> dict | None:
    """Celery task: run the full analysis pipeline for one job.

    Replaces `_process_analyze_job` from app.jobs. The actual pipeline
    logic is delegated to the existing worker functions. Progress is
    written to Postgres (via repository) and published to Redis pub/sub
    (for WebSocket relay).
    """
    logger.info("task start job_id=%s", job_id)

    try:
        # Initialize DB in the worker process on first task
        try:
            from app.db import init_db as _init_db
            _init_db()
        except Exception:
            logger.warning("DB init failed in worker (may not be available)")

        # Import the existing pipeline functions (same logic, different transport)
        from app.analyze_audio import build_lesson_json_from_librosa
        from app.audio_processing import prepare_audio_input
        from app.cache import (
            invalidate_cache_for_wav,
            load_cached_lesson_for_wav,
            reuse_cached_artifacts_into_job,
            save_cached_lesson_for_wav,
        )
        from app.coach import hydrate_coach_copy_into_sections
        from app.demucs_engine import DemucsEngineError, build_stem_routing_hints
        from app.ingest import (
            AUDIO_TOO_SHORT_USER_MESSAGE,
            AudioTooShortError,
            IngestError,
            YouTubeUrlInvalidError,
            get_data_dir,
            get_job_dir,
            resolve_lesson_titles,
        )
        from app.jobs import (
            ANALYSIS_FAILED_USER_MESSAGE,
            ANALYZE_ERROR_ANALYSIS_FAILED,
            ANALYZE_ERROR_AUDIO_TOO_LONG,
            ANALYZE_ERROR_AUDIO_TOO_SHORT,
            ANALYZE_ERROR_INGEST_FAILED,
            ANALYZE_ERROR_STEM_SEPARATION_FAILED,
            ANALYZE_ERROR_YOUTUBE_INVALID,
            AUDIO_TOO_LONG_USER_MESSAGE,
            FORCED_EXCEPTION_INPUT,
            MAX_ANALYZE_DURATION_SECONDS,
            PROCESSING_SLEEP_SECONDS,
            STEM_SEPARATION_FAILED_USER_MESSAGE,
            YOUTUBE_URL_INVALID_USER_MESSAGE,
            _lesson_with_skeleton_coach,
            _set_coach_pending,
        )
        from app.repository import (
            complete_job as _repo_complete,
            fail_job as _repo_fail,
            update_job_progress as _repo_progress,
        )
        from app.schemas import (
            CoachFocusArea,
            JobStatus,
            LessonJSON,
            LessonSectionStub,
            PlayerProfile,
            StemRoutingHints,
        )
        from app.separate import SeparationError, separate_song_to_stems
        from app.stem_quality import classify_stems_for_lesson

        worker_start = time.time()

        # Duration check
        _repo_progress(job_id, progress=0.05, stage_label="Queued\u2026")
        _publish_progress(job_id, "processing", progress=0.05, stage_label="Queued\u2026")
        time.sleep(PROCESSING_SLEEP_SECONDS)

        if youtube_url == FORCED_EXCEPTION_INPUT:
            raise RuntimeError("Forced exception from request payload")

        # Ingest
        _repo_progress(job_id, progress=0.12, stage_label="Preparing audio\u2026")
        _publish_progress(job_id, "processing", progress=0.12, stage_label="Preparing audio\u2026")
        ingest_start = time.time()
        prepared = prepare_audio_input(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
        )
        ingest_elapsed = time.time() - ingest_start
        wav_path_obj = prepared.normalized_wav_path
        source_metadata = prepared.source_metadata
        chunk_paths = prepared.chunk_paths
        wav_path = str(wav_path_obj)

        # Audio duration check
        wav_duration = prepared.duration_seconds
        if wav_duration > MAX_ANALYZE_DURATION_SECONDS:
            _repo_fail(job_id, AUDIO_TOO_LONG_USER_MESSAGE, error_code=ANALYZE_ERROR_AUDIO_TOO_LONG)
            _publish_progress(job_id, "failed", error=AUDIO_TOO_LONG_USER_MESSAGE)
            return None

        _repo_progress(job_id, progress=0.28, stage_label="Audio ready")
        _publish_progress(job_id, "processing", progress=0.28, stage_label="Audio ready")

        # Cache check
        cached_lesson = load_cached_lesson_for_wav(wav_path_obj)
        if cached_lesson is not None:
            reused = reuse_cached_artifacts_into_job(cached_lesson, job_id=job_id)
            if reused is not None:
                _repo_complete(job_id, reused)
                _publish_progress(job_id, "complete", result=reused.model_dump(exclude_none=True))
                logger.info("task complete (cache hit) job_id=%s", job_id)
                return reused.model_dump(exclude_none=True)
            invalidate_cache_for_wav(wav_path_obj)

        job_dir = get_job_dir(job_id)

        # Stem separation
        _repo_progress(job_id, progress=0.4, stage_label="Separating stems\u2026", analysis_stage="stems_separating")
        _publish_progress(job_id, "processing", progress=0.4, stage_label="Separating stems\u2026")
        stem_start = time.time()
        stems = separate_song_to_stems(wav_path_obj, job_dir, chunk_paths=chunk_paths)
        stem_elapsed = time.time() - stem_start

        _repo_progress(job_id, progress=0.62, stage_label="Stems ready", analysis_stage="stems_separating")
        _publish_progress(job_id, "processing", progress=0.62, stage_label="Stems ready")

        backend_root = get_data_dir().parent
        stem_abs_paths = {k: backend_root / rel for k, rel in stems.items()}
        stem_classification = classify_stems_for_lesson(wav_path_obj, stem_abs_paths)

        # Stem routing
        routing_hints = StemRoutingHints()
        try:
            hints_raw = build_stem_routing_hints(stem_abs_paths, stem_classification=stem_classification)
            routing_hints = StemRoutingHints(**hints_raw)
        except DemucsEngineError as exc:
            logger.info("stem routing hints unavailable job_id=%s: %s", job_id, exc)
        try:
            (job_dir / "stem_routing.json").write_text(
                routing_hints.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            logger.debug("failed to persist stem_routing.json job_id=%s", job_id, exc_info=True)

        guitar_rel_path = stems.get("guitar")
        vocals_rel_path = stems.get("vocals")

        if not guitar_rel_path:
            from app.jobs import _stub_lesson
            result = _stub_lesson(job_id, youtube_url, wav_path=wav_path, stems=stems, source_metadata=source_metadata)
        else:
            guitar_stem_path = backend_root / guitar_rel_path
            vocals_stem_path = backend_root / vocals_rel_path if vocals_rel_path else None
            piano_rel = stems.get("piano")
            piano_stem_path = (backend_root / piano_rel) if piano_rel else None
            analyze_start = time.time()

            def on_stage(stage, prog, label):
                _repo_progress(job_id, progress=prog, stage_label=label, analysis_stage=stage)
                _publish_progress(job_id, "processing", progress=prog, stage_label=label)

            result = build_lesson_json_from_librosa(
                job_id,
                guitar_stem_path=guitar_stem_path,
                vocals_stem_path=vocals_stem_path,
                stems=stems,
                wav_path=wav_path,
                source_url=youtube_url,
                player_profile=PlayerProfile(**player_profile) if player_profile else None,
                source_metadata=source_metadata,
                stem_classification=stem_classification,
                mix_wav_path=wav_path_obj,
                piano_stem_path=piano_stem_path,
                on_stage=on_stage,
                routing_hints=routing_hints,
                stem_abs_paths=stem_abs_paths,
            )
            analyze_elapsed = time.time() - analyze_start

        skeleton_result = _lesson_with_skeleton_coach(result)

        # Cache result
        save_cached_lesson_for_wav(wav_path_obj, skeleton_result)

        # Complete job
        _repo_complete(job_id, skeleton_result)
        _publish_progress(job_id, "complete", result=skeleton_result.model_dump(exclude_none=True))

        _set_coach_pending(job_id, len(skeleton_result.sections))
        # Kick off coach hydration as a separate Celery task
        hydrate_coach_task.delay(
            job_id,
            player_profile=player_profile,
            focus_area=focus_area,
        )

        logger.info("task complete job_id=%s total=%.2fs", job_id, time.time() - worker_start)
        return skeleton_result.model_dump(exclude_none=True)

    except YouTubeUrlInvalidError:
        _repo_fail(job_id, YOUTUBE_URL_INVALID_USER_MESSAGE, error_code=ANALYZE_ERROR_YOUTUBE_INVALID)
        _publish_progress(job_id, "failed", error=YOUTUBE_URL_INVALID_USER_MESSAGE)
    except AudioTooShortError:
        _repo_fail(job_id, AUDIO_TOO_SHORT_USER_MESSAGE, error_code=ANALYZE_ERROR_AUDIO_TOO_SHORT)
        _publish_progress(job_id, "failed", error=AUDIO_TOO_SHORT_USER_MESSAGE)
    except IngestError:
        _repo_fail(job_id, ANALYSIS_FAILED_USER_MESSAGE, error_code=ANALYZE_ERROR_INGEST_FAILED)
        _publish_progress(job_id, "failed", error=ANALYSIS_FAILED_USER_MESSAGE)
    except SeparationError:
        _repo_fail(job_id, STEM_SEPARATION_FAILED_USER_MESSAGE, error_code=ANALYZE_ERROR_STEM_SEPARATION_FAILED)
        _publish_progress(job_id, "failed", error=STEM_SEPARATION_FAILED_USER_MESSAGE)
    except Exception as exc:
        logger.exception("task failed job_id=%s", job_id)
        _repo_fail(job_id, ANALYSIS_FAILED_USER_MESSAGE, error_code=ANALYZE_ERROR_ANALYSIS_FAILED)
        _publish_progress(job_id, "failed", error=ANALYSIS_FAILED_USER_MESSAGE)
        try:
            raise self.retry(exc=exc)
        except Exception:
            pass

    return None


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def hydrate_coach_task(
    self,
    job_id: str,
    player_profile: dict | None = None,
    focus_area: str | None = None,
) -> None:
    """Celery task: hydrate coach copy into lesson sections."""
    logger.info("coach task start job_id=%s", job_id)
    try:
        from app.db import init_db as _init_db
        _init_db()
    except Exception:
        logger.warning("init_db failed job_id=%s", job_id, exc_info=True)
    from app.jobs import _hydrate_coach_copy_job
    from app.schemas import CoachFocusArea, PlayerProfile
    pp = PlayerProfile(**player_profile) if player_profile else None
    fa = focus_area
    _hydrate_coach_copy_job(job_id, player_profile=pp, focus_area=fa)


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def enrich_chord_timeline_task(self, job_id: str) -> None:
    """Celery task: enrich chord timeline with LLM correction."""
    logger.info("enrich task start job_id=%s", job_id)
    try:
        from app.db import init_db as _init_db
        _init_db()
    except Exception:
        logger.warning("init_db failed job_id=%s", job_id, exc_info=True)
    from app.jobs import _enrich_chord_timeline_job
    _enrich_chord_timeline_job(job_id, api_key=os.getenv("ANTHROPIC_API_KEY", ""))


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def beat_grid_recompute_task(
    self,
    job_id: str,
    time_signature: str | None = None,
    bpm_override: float | None = None,
) -> None:
    """Celery task: recompute beat grid and dependent artifacts."""
    logger.info("recompute task start job_id=%s", job_id)
    try:
        from app.db import init_db as _init_db
        _init_db()
    except Exception:
        logger.warning("init_db failed job_id=%s", job_id, exc_info=True)
    from app.jobs import _process_beat_grid_recompute
    _process_beat_grid_recompute(job_id, time_signature=time_signature, bpm_override=bpm_override)
