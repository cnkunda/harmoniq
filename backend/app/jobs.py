"""Background jobs for analysis — Redis-backed with Celery dispatch.

This implements PRIORITIES §4:
* POST /analyze returns a job_id immediately
* a worker transitions job status:
  processing -> complete | failed
* failed jobs store a user-safe error string

Phase 2: In-memory dict replaced with Redis (job_store).
Celery dispatch replaces threading when Redis is available.
"""

from __future__ import annotations

import logging
import threading
import time

from app.schemas import (
    AnalysisStage,
    CoachFocusArea,
    CoachHydrationSection,
    CoachHydrationStatus,
    JobStatus,
    LessonJSON,
    LessonSectionStub,
    PlayerProfile,
)

from app.analyze_audio import build_lesson_json_from_librosa
from app.cache import invalidate_cache_for_wav, load_cached_lesson_for_wav, reuse_cached_artifacts_into_job, save_cached_lesson_for_wav
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
    wav_file_duration_seconds,
)

from app.separate import SeparationError, separate_song_to_stems
from app.stem_quality import classify_stems_for_lesson

logger = logging.getLogger("harmoniq.jobs")
logger.setLevel(logging.INFO)

# Stable `JobStatus.error_code` when status=failed — keep in sync with `mapAnalyzeFlowError` (client).
ANALYZE_ERROR_YOUTUBE_INVALID = "youtube_invalid"
ANALYZE_ERROR_AUDIO_TOO_SHORT = "audio_too_short"
ANALYZE_ERROR_AUDIO_TOO_LONG = "audio_too_long"
ANALYZE_ERROR_INGEST_FAILED = "ingest_failed"
ANALYZE_ERROR_STEM_SEPARATION_FAILED = "stem_separation_failed"
ANALYZE_ERROR_ANALYSIS_FAILED = "analysis_failed"

# ---------------------------------------------------------------------------
# Job store abstraction (Redis when available, in-memory fallback)
# ---------------------------------------------------------------------------

_redis_available: bool | None = None


def _check_redis() -> bool:
    """Check if Redis is available; cache the result."""
    global _redis_available
    if _redis_available is not None:
        return _redis_available
    try:
        from app.job_store import ping
        _redis_available = ping()
    except Exception:
        _redis_available = False
    return _redis_available


def _use_redis() -> bool:
    """Return True if we should use Redis-backed store."""
    import os
    # Force in-memory if explicitly disabled
    if os.getenv("HARMONIQ_USE_REDIS", "auto").lower() in ("0", "false", "no"):
        return False
    return _check_redis()


# In-memory fallback (when Redis is unavailable)
_jobs_memory: dict[str, JobStatus] = {}
_coach_memory: dict[str, CoachHydrationStatus] = {}


def _get_job(job_id: str) -> JobStatus | None:
    if _use_redis():
        from app.job_store import get_job
        return get_job(job_id)
    return _jobs_memory.get(job_id)


def _set_job(job_id: str, status: JobStatus) -> None:
    if _use_redis():
        from app.job_store import set_job_status
        set_job_status(job_id, status)
    else:
        _jobs_memory[job_id] = status


def _update_job(job_id: str, **fields) -> None:
    if _use_redis():
        from app.job_store import update_job
        update_job(job_id, **fields)
    else:
        current = _jobs_memory.get(job_id)
        if current is not None:
            data = current.model_dump()
            data.update({k: v for k, v in fields.items() if v is not None})
            _jobs_memory[job_id] = JobStatus(**data)


def _get_coach(job_id: str) -> CoachHydrationStatus | None:
    if _use_redis():
        from app.job_store import get_coach_hydration
        return get_coach_hydration(job_id)
    return _coach_memory.get(job_id)


def _set_coach(job_id: str, status: CoachHydrationStatus) -> None:
    if _use_redis():
        from app.job_store import set_coach_hydration
        set_coach_hydration(job_id, status)
    else:
        _coach_memory[job_id] = status


def _publish_sse(job_id: str, event: str, data: dict) -> None:
    """Publish an SSE event if Redis is available."""
    if _use_redis():
        try:
            from app.job_store import publish_sse_event
            publish_sse_event(job_id, event, data)
        except Exception:
            pass  # SSE failure should not block the pipeline


# ---------------------------------------------------------------------------
# Progress reporting with stage tracking
# ---------------------------------------------------------------------------

def _set_job_processing_progress(
    job_id: str,
    progress: float,
    stage_label: str,
    analysis_stage: AnalysisStage | None = None,
) -> None:
    """Update progress for an in-flight job; no-op if missing or not processing."""
    current = _get_job(job_id)
    if current is None or current.status != "processing":
        return
    started = current.processing_started_at
    if started is None:
        started = time.time()

    progress_val = max(0.0, min(1.0, float(progress)))
    fields = {
        "status": "processing",
        "result": None,
        "error": None,
        "progress": progress_val,
        "stage_label": stage_label,
        "processing_started_at": float(started),
    }
    if analysis_stage is not None:
        fields["analysis_stage"] = analysis_stage

    if _use_redis():
        from app.job_store import set_job_progress
        set_job_progress(job_id, progress_val, stage_label, analysis_stage)
    else:
        _jobs_memory[job_id] = JobStatus(**fields)

    # Publish SSE progress event
    _publish_sse(job_id, "progress", {
        "progress": progress_val,
        "stage_label": stage_label,
        "analysis_stage": analysis_stage,
    })


# ---------------------------------------------------------------------------
# Lesson helpers
# ---------------------------------------------------------------------------

def _lesson_with_skeleton_coach(lesson: LessonJSON) -> LessonJSON:
    sections: list[LessonSectionStub] = []
    for sec in lesson.sections:
        payload = sec.model_dump(exclude_none=True)
        payload["coach_note"] = ""
        payload["coach_explanation"] = ""
        sections.append(LessonSectionStub(**payload))
    return lesson.model_copy(update={"sections": sections})


def _set_coach_pending(job_id: str, section_count: int) -> None:
    _set_coach(
        job_id,
        CoachHydrationStatus(
            status="pending",
            sections=[CoachHydrationSection(index=i, coach_note="", coach_explanation="") for i in range(max(0, section_count))],
            fallback_reason=None,
        ),
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
    focus_area: CoachFocusArea | None = None,
) -> None:
    job = _get_job(job_id)
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
        focus_area=focus_area,
    )
    patched = lesson.model_copy(update={"sections": enriched})
    _set_job(job_id, JobStatus(status="complete", result=patched, error=None))
    _set_coach(
        job_id,
        CoachHydrationStatus(
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
        ),
    )
    _publish_sse(job_id, "complete", {"job_id": job_id, "status": "complete"})
    logger.info("coach_hydration complete job_id=%s status=%s fallback_reason=%s", job_id, status, fallback_reason)


def get_coach_hydration(job_id: str) -> CoachHydrationStatus | None:
    return _get_coach(job_id)


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

# Maximum audio duration for analysis (5 minutes) to prevent excessive processing time
MAX_ANALYZE_DURATION_SECONDS = 300

# User-facing error message for audio too long
AUDIO_TOO_LONG_USER_MESSAGE = (
    "Audio is too long for analysis. Please use a clip under 5 minutes."
)

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
    focus_area: CoachFocusArea | None = None,
) -> None:
    """Worker loop for one analyze job.

    Uses Redis-backed job store when available, falls back to in-memory.
    Each major stage is timed and reported via progress updates.
    """
    worker_start = time.time()
    logger.info("worker start job_id=%s youtube_url=%r upload_path=%r", job_id, youtube_url, upload_path)
    time.sleep(PROCESSING_SLEEP_SECONDS)

    try:
        if youtube_url == FORCED_EXCEPTION_INPUT:
            raise RuntimeError("Forced exception from request payload")

        from app.ingest import ingest_youtube_or_upload_to_wav

        _set_job_processing_progress(job_id, 0.12, "Preparing audio…", "ingesting")
        ingest_start = time.time()
        wav_path_obj, source_metadata = ingest_youtube_or_upload_to_wav(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
        )
        ingest_elapsed = time.time() - ingest_start
        logger.info("ingest completed in %.2fs job_id=%s", ingest_elapsed, job_id)
        wav_path = str(wav_path_obj)

        wav_duration = wav_file_duration_seconds(wav_path_obj)
        if wav_duration is not None and wav_duration > MAX_ANALYZE_DURATION_SECONDS:
            logger.warning(
                "Audio too long: %.1fs > %ds job_id=%s",
                wav_duration,
                MAX_ANALYZE_DURATION_SECONDS,
                job_id,
            )
            _set_job(
                job_id,
                JobStatus(
                    status="failed",
                    result=None,
                    error=AUDIO_TOO_LONG_USER_MESSAGE,
                    error_code=ANALYZE_ERROR_AUDIO_TOO_LONG,
                ),
            )
            _publish_sse(job_id, "error", {"error": AUDIO_TOO_LONG_USER_MESSAGE, "error_code": ANALYZE_ERROR_AUDIO_TOO_LONG})
            return

        _set_job_processing_progress(job_id, 0.28, "Audio ready", "ingesting")
        cache_check_start = time.time()
        cached_lesson = load_cached_lesson_for_wav(wav_path_obj, player_profile=player_profile)
        cache_check_elapsed = time.time() - cache_check_start
        logger.info("cache check completed in %.2fs job_id=%s hit=%s", cache_check_elapsed, job_id, cached_lesson is not None)

        if cached_lesson is not None:
            reuse_start = time.time()
            reused = reuse_cached_artifacts_into_job(cached_lesson, job_id=job_id)
            reuse_elapsed = time.time() - reuse_start
            logger.info("cache reuse completed in %.2fs job_id=%s", reuse_elapsed, job_id)

            if reused is not None:
                _set_job(job_id, JobStatus(status="complete", result=reused, error=None))
                if _lesson_has_hydrated_coach(reused):
                    _set_coach(
                        job_id,
                        CoachHydrationStatus(
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
                        ),
                    )
                else:
                    _set_coach_pending(job_id, len(reused.sections))
                    coach_thread = threading.Thread(
                        target=_hydrate_coach_copy_job,
                        kwargs={"job_id": job_id, "player_profile": player_profile, "focus_area": focus_area},
                        daemon=True,
                    )
                    coach_thread.start()
                _publish_sse(job_id, "complete", {"job_id": job_id, "status": "complete"})
                total_elapsed = time.time() - worker_start
                logger.info("worker complete (cache hit) job_id=%s total=%.2fs", job_id, total_elapsed)
                return

            logger.warning(
                "cache artifacts missing for job_id=%s; invalidating cache entry and re-analyzing",
                job_id,
            )
            invalidate_cache_for_wav(wav_path_obj, player_profile=player_profile)

        job_dir = get_job_dir(job_id)
        _set_job_processing_progress(job_id, 0.4, "Separating stems…", "stems_separating")
        stem_start = time.time()
        stems = separate_song_to_stems(wav_path_obj, job_dir)
        stem_elapsed = time.time() - stem_start
        logger.info("stem separation completed in %.2fs job_id=%s", stem_elapsed, job_id)
        _set_job_processing_progress(job_id, 0.62, "Stems ready", "stems_separating")
        backend_root = get_data_dir().parent
        stem_abs_paths = {k: backend_root / rel for k, rel in stems.items()}
        classify_start = time.time()
        stem_classification = classify_stems_for_lesson(wav_path_obj, stem_abs_paths)
        classify_elapsed = time.time() - classify_start
        logger.info("stem classification completed in %.2fs job_id=%s", classify_elapsed, job_id)
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
            stub_start = time.time()
            stub = _stub_lesson(
                job_id,
                youtube_url,
                wav_path=wav_path,
                stems=stems,
                source_metadata=source_metadata,
            )
            stub_elapsed = time.time() - stub_start
            logger.info("stub lesson generated in %.2fs job_id=%s", stub_elapsed, job_id)
            result = stub
        else:
            _set_job_processing_progress(job_id, 0.78, "Analyzing structure & tabs…", "chords_inferring")
            guitar_stem_path = backend_root / guitar_rel_path
            vocals_stem_path = backend_root / vocals_rel_path if vocals_rel_path else None
            piano_rel = stems.get("piano")
            piano_stem_path = (backend_root / piano_rel) if piano_rel else None
            analyze_start = time.time()

            def _analysis_progress_callback(stage: str, partial: LessonJSON | None) -> None:
                """Set intermediate results as each analysis stage completes."""
                if stage == "chords_inferring":
                    _set_job_processing_progress(job_id, 0.82, "Chord timeline ready", "chords_inferring")
                    _publish_sse(job_id, "stage", {"stage": "chords_inferring"})
                elif stage == "solo_inferring":
                    _set_job_processing_progress(job_id, 0.88, "Solo notes ready", "solo_inferring")
                    _publish_sse(job_id, "stage", {"stage": "solo_inferring"})
                elif stage == "building_musicxml":
                    _set_job_processing_progress(job_id, 0.94, "Building score…", "building_musicxml")
                    _publish_sse(job_id, "stage", {"stage": "building_musicxml"})

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
                progress_callback=_analysis_progress_callback,
            )
            analyze_elapsed = time.time() - analyze_start
            logger.info("librosa analysis completed in %.2fs job_id=%s", analyze_elapsed, job_id)
        skeleton_start = time.time()
        skeleton_result = _lesson_with_skeleton_coach(result)
        skeleton_elapsed = time.time() - skeleton_start
        logger.info("skeleton coach preparation completed in %.2fs job_id=%s", skeleton_elapsed, job_id)

        # ── Commit 114: LLM Chord Enrichment (background, non-blocking) ──
        try:
            from app.chord_enrichment import enrich_chord_timeline

            # Extract chord timeline and key from the result for enrichment
            enrichment_key = getattr(result, "key", None)
            enrichment_timeline = None
            for sec in skeleton_result.sections:
                sec_dict = sec.model_dump(exclude_none=True)
                if "chord_timeline" in sec_dict:
                    from app.schemas import ChordTimeline
                    enrichment_timeline = ChordTimeline.model_validate(sec_dict["chord_timeline"])
                    break

            if enrichment_timeline and enrichment_timeline.events:
                enriched_timeline, enrichment_metrics = enrich_chord_timeline(
                    enrichment_timeline,
                    key_signature=enrichment_key,
                )
                # Apply enriched Roman numerals back to sections
                for sec in skeleton_result.sections:
                    sec_dict = sec.model_dump(exclude_none=True)
                    if "chord_timeline" in sec_dict:
                        # Update chord events with enrichment data
                        updated_events = []
                        for ev in enriched_timeline.events:
                            updated_events.append(ev.model_dump())
                        sec_dict["chord_timeline"]["events"] = updated_events
                        # Reconstruct section with enriched data
                        from app.schemas import LessonSectionStub
                        patched = LessonSectionStub(**sec_dict)
                        idx = skeleton_result.sections.index(sec)
                        skeleton_result.sections[idx] = patched
                        break
                logger.info(
                    "chord_enrichment_sync job_id=%s applied=%d roman=%d",
                    job_id,
                    enrichment_metrics.get("enrichment_applied", 0),
                    enrichment_metrics.get("roman_numerals_assigned", 0),
                )
        except Exception:
            logger.debug("chord_enrichment skipped job_id=%s", job_id, exc_info=True)

        # Persist intermediate artifacts to disk for restart survival
        try:
            from app.routers.analyze import _persist_artifacts_to_disk
            from app.analysis_store import save_beat_grid
            from app.schemas import BeatGrid, ChordTimeline, SoloNotes
            ct = None
            sn = None
            bg = None
            # Extract artifacts from sections if available
            for sec in skeleton_result.sections:
                sec_dict = sec.model_dump(exclude_none=True)
                if "beat_grid" in sec_dict and bg is None:
                    bg = BeatGrid.model_validate(sec_dict["beat_grid"])
                if "chord_timeline" in sec_dict and ct is None:
                    ct = ChordTimeline.model_validate(sec_dict["chord_timeline"])
                if "solo_notes" in sec_dict and sn is None:
                    sn = SoloNotes.model_validate(sec_dict["solo_notes"])
            _persist_artifacts_to_disk(
                job_dir,
                beat_grid=bg,
                chord_timeline=ct,
                solo_notes=sn,
            )
            # Also save lesson.json
            with open(job_dir / "lesson.json", "w") as f:
                f.write(skeleton_result.model_dump_json(indent=2))
            logger.info("intermediate artifacts persisted job_id=%s", job_id)
        except Exception:
            logger.exception("failed to persist intermediate artifacts job_id=%s", job_id)

        cache_save_start = time.time()
        save_cached_lesson_for_wav(wav_path_obj, skeleton_result, player_profile=player_profile)
        cache_save_elapsed = time.time() - cache_save_start
        logger.info("lesson cache save completed in %.2fs job_id=%s", cache_save_elapsed, job_id)

        _set_job(job_id, JobStatus(status="complete", result=skeleton_result, error=None))
        _set_coach_pending(job_id, len(skeleton_result.sections))
        coach_thread = threading.Thread(
            target=_hydrate_coach_copy_job,
            kwargs={"job_id": job_id, "player_profile": player_profile, "focus_area": focus_area},
            daemon=True,
        )
        coach_thread.start()
        _publish_sse(job_id, "complete", {"job_id": job_id, "status": "complete"})
        total_elapsed = time.time() - worker_start
        logger.info(
            "worker complete job_id=%s total=%.2fs (ingest=%.2fs, stems=%.2fs, analyze=%.2fs)",
            job_id,
            total_elapsed,
            ingest_elapsed,
            stem_elapsed,
            analyze_elapsed,
        )
    except YouTubeUrlInvalidError:
        logger.warning("worker failed job_id=%s invalid youtube_url", job_id)
        _set_job(
            job_id,
            JobStatus(
                status="failed",
                result=None,
                error=YOUTUBE_URL_INVALID_USER_MESSAGE,
                error_code=ANALYZE_ERROR_YOUTUBE_INVALID,
            ),
        )
        _publish_sse(job_id, "error", {"error": YOUTUBE_URL_INVALID_USER_MESSAGE, "error_code": ANALYZE_ERROR_YOUTUBE_INVALID})
    except AudioTooShortError:
        logger.warning("worker failed job_id=%s audio too short", job_id)
        _set_job(
            job_id,
            JobStatus(
                status="failed",
                result=None,
                error=AUDIO_TOO_SHORT_USER_MESSAGE,
                error_code=ANALYZE_ERROR_AUDIO_TOO_SHORT,
            ),
        )
        _publish_sse(job_id, "error", {"error": AUDIO_TOO_SHORT_USER_MESSAGE, "error_code": ANALYZE_ERROR_AUDIO_TOO_SHORT})
    except IngestError:
        logger.exception("worker failed job_id=%s ingest error", job_id)
        _set_job(
            job_id,
            JobStatus(
                status="failed",
                result=None,
                error=ANALYSIS_FAILED_USER_MESSAGE,
                error_code=ANALYZE_ERROR_INGEST_FAILED,
            ),
        )
        _publish_sse(job_id, "error", {"error": ANALYSIS_FAILED_USER_MESSAGE, "error_code": ANALYZE_ERROR_INGEST_FAILED})
    except SeparationError:
        logger.exception("worker failed job_id=%s stem separation error", job_id)
        _set_job(
            job_id,
            JobStatus(
                status="failed",
                result=None,
                error=STEM_SEPARATION_FAILED_USER_MESSAGE,
                error_code=ANALYZE_ERROR_STEM_SEPARATION_FAILED,
            ),
        )
        _publish_sse(job_id, "error", {"error": STEM_SEPARATION_FAILED_USER_MESSAGE, "error_code": ANALYZE_ERROR_STEM_SEPARATION_FAILED})
    except Exception:
        logger.exception("worker failed job_id=%s", job_id)
        _set_job(
            job_id,
            JobStatus(
                status="failed",
                result=None,
                error=ANALYSIS_FAILED_USER_MESSAGE,
                error_code=ANALYZE_ERROR_ANALYSIS_FAILED,
            ),
        )
        _publish_sse(job_id, "error", {"error": ANALYSIS_FAILED_USER_MESSAGE, "error_code": ANALYZE_ERROR_ANALYSIS_FAILED})


def enqueue_analyze_job(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
    player_profile: PlayerProfile | None = None,
    focus_area: CoachFocusArea | None = None,
) -> None:
    """Mark job as processing and dispatch to worker.

    Tries Celery dispatch first; falls back to threading if Redis is unavailable.
    """
    _set_job(
        job_id,
        JobStatus(
            status="processing",
            result=None,
            error=None,
            progress=0.05,
            stage_label="Queued…",
            processing_started_at=time.time(),
        ),
    )
    _set_coach(job_id, CoachHydrationStatus(status="pending", sections=[], fallback_reason=None))

    logger.info(
        "enqueue job_id=%s status=processing youtube_url=%r upload_path=%r has_profile=%s redis=%s",
        job_id,
        youtube_url,
        upload_path,
        player_profile is not None,
        _use_redis(),
    )

    # Try Celery dispatch when Redis is available
    if _use_redis():
        try:
            from app.tasks import process_analyze_job

            player_dict = player_profile.model_dump() if player_profile else None
            process_analyze_job.delay(
                job_id,
                youtube_url=youtube_url,
                upload_path=upload_path,
                player_profile=player_dict,
                focus_area=focus_area.value if focus_area else None,
            )
            logger.info("dispatched_to_celery job_id=%s", job_id)
            return
        except Exception as exc:
            logger.warning("celery_dispatch_failed job_id=%s exception=%s; falling back to thread", job_id, type(exc).__name__)

    # Fallback: thread-based execution (single process)
    t = threading.Thread(
        target=_process_analyze_job,
        kwargs={
            "job_id": job_id,
            "youtube_url": youtube_url,
            "upload_path": upload_path,
            "player_profile": player_profile,
            "focus_area": focus_area,
        },
        daemon=True,
    )
    t.start()


# ---------------------------------------------------------------------------
# Backwards compatibility: expose `jobs` dict for existing test imports
# ---------------------------------------------------------------------------

class _JobsProxy:
    """Dict-like proxy that delegates to Redis or in-memory store.

    Maintains the `jobs[job_id] = ...` interface used by existing tests
    and routers, while routing reads/writes to the appropriate backend.
    """

    def __getitem__(self, key: str) -> JobStatus:
        job = _get_job(key)
        if job is None:
            raise KeyError(key)
        return job

    def __setitem__(self, key: str, value: JobStatus) -> None:
        _set_job(key, value)

    def __contains__(self, key: str) -> bool:
        return _get_job(key) is not None

    def get(self, key: str, default=None) -> JobStatus | None:
        job = _get_job(key)
        return job if job is not None else default

    def __len__(self) -> int:
        # Approximate for in-memory; Redis would need SCAN
        if _use_redis():
            return -1  # Unknown
        return len(_jobs_memory)

    def clear(self) -> None:
        """Delete all job state (test fixtures and admin routes)."""
        if _use_redis():
            from app.job_store import get_redis
            r = get_redis()
            keys = list(r.scan_iter(match="job:*"))
            if keys:
                r.delete(*keys)
        else:
            _jobs_memory.clear()


jobs = _JobsProxy()


class _CoachProxy:
    """Dict-like proxy for coach hydration state (backend-agnostic)."""

    def __getitem__(self, key: str) -> CoachHydrationStatus:
        status = _get_coach(key)
        if status is None:
            raise KeyError(key)
        return status

    def __setitem__(self, key: str, value: CoachHydrationStatus) -> None:
        _set_coach(key, value)

    def __contains__(self, key: str) -> bool:
        return _get_coach(key) is not None

    def get(self, key: str, default=None) -> CoachHydrationStatus | None:
        status = _get_coach(key)
        return status if status is not None else default

    def clear(self) -> None:
        if _use_redis():
            from app.job_store import get_redis
            r = get_redis()
            keys = list(r.scan_iter(match="coach:*"))
            if keys:
                r.delete(*keys)
        else:
            _coach_memory.clear()


coach_hydration = _CoachProxy()
