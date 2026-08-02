"""In-memory background jobs for analysis.

This implements PRIORITIES §4:
* POST /analyze returns a job_id immediately
* a worker transitions job status:
  processing -> complete | failed
* failed jobs store a user-safe error string

Scope note: single-process in-memory store is intentional for v1.
Commit 110: completed/failed jobs are persisted to disk as JobStatus.json
so they survive server restarts.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from app.analyze_audio import build_lesson_json_from_librosa
from app.audio_mix import mix_stems, resolve_chord_stems, resolve_solo_stem
from app.audio_processing import AudioPreparationError, prepare_audio_input
from app.cache import (invalidate_cache_for_wav, load_cached_lesson_for_wav,
                       reuse_cached_artifacts_into_job,
                       save_cached_lesson_for_wav)
from app.chord_enrichment import enrich_chord_timeline
from app.coach import hydrate_coach_copy_into_sections
from app.demucs_engine import DemucsEngineError, build_stem_routing_hints
from app.ingest import (AUDIO_TOO_SHORT_USER_MESSAGE, AudioTooShortError,
                        IngestError, SourceMetadata, YouTubeUrlInvalidError,
                        get_data_dir, get_job_dir, resolve_lesson_titles,
                        wav_file_duration_seconds)
from app.schemas import (BeatGrid, BeatGridRecomputeResponse,
                         ChordEnrichmentStatus, CoachFocusArea,
                         CoachHydrationSection, CoachHydrationStatus,
                         JobStatus, LessonJSON, LessonSectionStub,
                         PlayerProfile, StemRoutingHints)
from app.separate import SeparationError, separate_song_to_stems
from app.stem_quality import classify_stems_for_lesson

try:
    from app.repository import (
        complete_job as _repo_complete_job,
        create_job as _repo_create_job,
        fail_job as _repo_fail_job,
        get_job as _repo_get_job,
        get_chord_enrichment_status as _repo_get_chord_enrichment,
        get_coach_hydration_status as _repo_get_coach_hydration,
        get_recompute_job_status as _repo_get_recompute,
        update_job_progress as _repo_update_progress,
        upsert_chord_enrichment as _repo_upsert_chord_enrichment,
        upsert_coach_hydration as _repo_upsert_coach_hydration,
        upsert_recompute_job as _repo_upsert_recompute,
    )
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

logger = logging.getLogger("harmoniq.jobs")
logger.setLevel(logging.INFO)

# Stable `JobStatus.error_code` when status=failed — keep in sync with `mapAnalyzeFlowError` (client).
ANALYZE_ERROR_YOUTUBE_INVALID = "youtube_invalid"
ANALYZE_ERROR_AUDIO_TOO_SHORT = "audio_too_short"
ANALYZE_ERROR_AUDIO_TOO_LONG = "audio_too_long"
ANALYZE_ERROR_INGEST_FAILED = "ingest_failed"
ANALYZE_ERROR_STEM_SEPARATION_FAILED = "stem_separation_failed"
ANALYZE_ERROR_ANALYSIS_FAILED = "analysis_failed"

# In-memory job store (single process).
jobs: dict[str, JobStatus] = {}
coach_hydration: dict[str, CoachHydrationStatus] = {}
chord_enrichment: dict[str, ChordEnrichmentStatus] = {}


# ---- Commit 110: Disk persistence for completed/failed jobs ----

def save_job_to_disk(job_id: str) -> None:
    """Persist a completed or failed job to disk so it survives server restarts."""
    job = jobs.get(job_id)
    if job is None or job.status not in ("complete", "failed"):
        return
    try:
        job_dir = get_job_dir(job_id)
        payload = job.model_dump(exclude_none=True)
        (job_dir / "JobStatus.json").write_text(
            __import__("json").dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("job persisted to disk job_id=%s status=%s", job_id, job.status)
    except Exception:
        logger.exception("Failed to persist job to disk job_id=%s", job_id)


def load_jobs_from_disk() -> int:
    """Reload completed/failed jobs from disk on server startup. Returns count loaded."""
    data_dir = get_data_dir()
    jobs_dir = data_dir / "jobs"
    if not jobs_dir.exists():
        return 0
    loaded = 0
    import json as _json
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        status_file = job_dir / "JobStatus.json"
        if not status_file.exists():
            continue
        try:
            raw = _json.loads(status_file.read_text(encoding="utf-8"))
            job_id = job_dir.name
            job_status = JobStatus.model_validate(raw)
            if job_status.status in ("complete", "failed"):
                jobs[job_id] = job_status
                loaded += 1
        except Exception:
            logger.exception("Failed to reload job from disk: %s", job_dir.name)
    logger.info("loaded %d jobs from disk", loaded)
    return loaded


def _delete_job_from_disk(job_id: str) -> None:
    """Remove persisted job file from disk."""
    try:
        job_dir = get_job_dir(job_id)
        status_file = job_dir / "JobStatus.json"
        if status_file.exists():
            status_file.unlink()
            logger.info("job removed from disk job_id=%s", job_id)
    except Exception:
        logger.exception("Failed to remove job from disk job_id=%s", job_id)

# ---- End Commit 110 ----


def _persist_job_to_db(job_id: str) -> None:
    """Best-effort write the in-memory job state to Postgres."""
    if not _HAS_DB:
        return
    try:
        job = jobs.get(job_id)
        if job is None:
            return
        if job.status in ("complete", "failed"):
            if job.status == "complete" and job.result is not None:
                _repo_complete_job(job_id, job.result)
            else:
                _repo_fail_job(job_id, job.error or "Unknown error", error_code=job.error_code)
        else:
            _repo_update_progress(
                job_id,
                progress=job.progress,
                stage_label=job.stage_label,
                analysis_stage=job.analysis_stage,
            )
    except Exception:
        logger.warning("Failed to persist job to DB job_id=%s (non-fatal)", job_id)


def load_jobs_from_db() -> int:
    """Load active jobs from Postgres into the in-memory cache. Returns count loaded."""
    if not _HAS_DB:
        return 0
    try:
        from app.repository import list_active_jobs as _repo_list
        active = _repo_list()
        for js in active:
            jobs[js.job_id] = js
        count = len(active)
        if count:
            logger.info("Loaded %d jobs from database", count)
        return count
    except Exception:
        logger.exception("Failed to load jobs from database")
        return 0


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
        analysis_stage=current.analysis_stage,
    )
    _persist_job_to_db(job_id)


def _set_job_analysis_stage(
    job_id: str,
    analysis_stage: str,
    progress: float,
    stage_label: str,
    *,
    result: LessonJSON | None = None,
) -> None:
    """Update analysis_stage for an in-flight job; preserves existing result if not provided."""
    current = jobs.get(job_id)
    if current is None or current.status != "processing":
        return
    started = current.processing_started_at
    if started is None:
        started = time.time()
    jobs[job_id] = JobStatus(
        status="processing",
        result=result if result is not None else current.result,
        error=None,
        progress=max(0.0, min(1.0, float(progress))),
        stage_label=stage_label,
        processing_started_at=float(started),
        analysis_stage=analysis_stage,
    )
    _persist_job_to_db(job_id)


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
    _persist_coach_to_db(job_id)


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
        focus_area=focus_area,
    )
    patched = lesson.model_copy(update={"sections": enriched})
    jobs[job_id] = JobStatus(status="complete", result=patched, error=None)
    _persist_job_to_db(job_id)
    save_job_to_disk(job_id)
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
    _persist_coach_to_db(job_id)
    logger.info("coach_hydration complete job_id=%s status=%s fallback_reason=%s", job_id, status, fallback_reason)


def get_coach_hydration(job_id: str) -> CoachHydrationStatus | None:
    return coach_hydration.get(job_id)


# ---- Commit 116: Chord enrichment (LLM correction + Roman numerals) ----

def _set_chord_enrichment_pending(job_id: str) -> None:
    chord_enrichment[job_id] = ChordEnrichmentStatus(status="pending")
    _persist_enrichment_to_db(job_id)


def _enrich_chord_timeline_job(
    job_id: str,
    *,
    api_key: str = "",
) -> None:
    """Background worker: run LLM chord correction on the completed analysis."""
    job = jobs.get(job_id)
    if job is None or job.result is None:
        return

    chord_enrichment[job_id] = ChordEnrichmentStatus(status="processing")
    _persist_enrichment_to_db(job_id)
    lesson = job.result

    if not lesson.chord_timeline or not lesson.chord_timeline.events:
        chord_enrichment[job_id] = ChordEnrichmentStatus(
            status="skipped",
            fallback_reason="no_chord_timeline",
        )
        _persist_enrichment_to_db(job_id)
        return

    try:
        enriched_events, metrics = enrich_chord_timeline(
            list(lesson.chord_timeline.events),
            lesson.key or "C major",
            api_key=api_key,
        )

        # Patch lesson with enriched chord timeline
        enriched_timeline = lesson.chord_timeline.model_copy(
            update={"events": enriched_events}
        )
        patched = lesson.model_copy(update={"chord_timeline": enriched_timeline})
        jobs[job_id] = JobStatus(status="complete", result=patched, error=None)
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)

        chord_enrichment[job_id] = ChordEnrichmentStatus(
            status="complete",
            total_events=len(enriched_events),
            corrected_events=metrics.get("corrected_events", 0),
            llm_latency_p50=metrics.get("llm_latency_p50"),
            llm_latency_p95=metrics.get("llm_latency_p95"),
            fallback_reason=None,
        )
        _persist_enrichment_to_db(job_id)
        logger.info(
            "chord_enrichment complete job_id=%s corrected=%d/%d",
            job_id,
            metrics.get("corrected_events", 0),
            len(enriched_events),
        )
    except Exception:
        logger.exception("chord_enrichment failed job_id=%s", job_id)
        chord_enrichment[job_id] = ChordEnrichmentStatus(
            status="skipped",
            fallback_reason="exception",
        )
        _persist_enrichment_to_db(job_id)


def get_chord_enrichment(job_id: str) -> ChordEnrichmentStatus | None:
    return chord_enrichment.get(job_id)


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

# Maximum audio duration for analysis (10 minutes) to prevent excessive processing time
MAX_ANALYZE_DURATION_SECONDS = 600

# User-facing error message for audio too long
AUDIO_TOO_LONG_USER_MESSAGE = (
    "Audio is too long for analysis. Please use a clip under 10 minutes."
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
    focus_area: CoachFocusArea | None = None,
) -> None:
    """Worker loop for one analyze job.

    Thread-based on purpose: FastAPI `TestClient` polling can otherwise block
    asyncio task progress, causing jobs to remain stuck in `processing`.
    
    Performance logging: Each major stage is timed to identify bottlenecks.
    """
    worker_start = time.time()
    logger.info("worker start job_id=%s youtube_url=%r upload_path=%r", job_id, youtube_url, upload_path)
    time.sleep(PROCESSING_SLEEP_SECONDS)

    try:
        if youtube_url == FORCED_EXCEPTION_INPUT:
            # Smoke-test hook for PRIORITIES §4 acceptance criteria.
            raise RuntimeError("Forced exception from request payload")

        _set_job_processing_progress(job_id, 0.12, "Preparing audio…")
        ingest_start = time.time()
        prepared = prepare_audio_input(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
        )
        ingest_elapsed = time.time() - ingest_start
        logger.info("ingest completed in %.2fs job_id=%s", ingest_elapsed, job_id)
        wav_path_obj = prepared.normalized_wav_path
        source_metadata = prepared.source_metadata
        chunk_paths = prepared.chunk_paths
        wav_path = str(wav_path_obj)
        
        # Check audio duration before expensive processing
        wav_duration = prepared.duration_seconds
        if wav_duration > MAX_ANALYZE_DURATION_SECONDS:
            logger.warning(
                "Audio too long: %.1fs > %ds job_id=%s",
                wav_duration,
                MAX_ANALYZE_DURATION_SECONDS,
                job_id,
            )
            jobs[job_id] = JobStatus(
                status="failed",
                result=None,
                error=AUDIO_TOO_LONG_USER_MESSAGE,
                error_code=ANALYZE_ERROR_AUDIO_TOO_LONG,
            )
            _persist_job_to_db(job_id)
            return
        
        _set_job_processing_progress(job_id, 0.28, "Audio ready")
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
                jobs[job_id] = JobStatus(status="complete", result=reused, error=None)
                _persist_job_to_db(job_id)
                save_job_to_disk(job_id)
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
                    _persist_coach_to_db(job_id)
                else:
                    _set_coach_pending(job_id, len(reused.sections))
                    coach_thread = threading.Thread(
                        target=_hydrate_coach_copy_job,
                        kwargs={"job_id": job_id, "player_profile": player_profile, "focus_area": focus_area},
                        daemon=True,
                    )
                    coach_thread.start()
                total_elapsed = time.time() - worker_start
                logger.info("worker complete (cache hit) job_id=%s total=%.2fs", job_id, total_elapsed)
                return

            # Cache hit but artifacts missing — invalidate stale entry so
            # future attempts don't re-encounter the same dead reference.
            logger.warning(
                "cache artifacts missing for job_id=%s; invalidating cache entry and re-analyzing",
                job_id,
            )
            invalidate_cache_for_wav(wav_path_obj, player_profile=player_profile)

        job_dir = get_job_dir(job_id)
        _set_job_analysis_stage(job_id, "stems_separating", 0.4, "Separating stems…")
        stem_start = time.time()
        stems = separate_song_to_stems(wav_path_obj, job_dir, chunk_paths=chunk_paths)
        stem_elapsed = time.time() - stem_start
        logger.info("stem separation completed in %.2fs job_id=%s", stem_elapsed, job_id)
        _set_job_analysis_stage(job_id, "stems_separating", 0.62, "Stems ready")
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

        # Commit 111: Build stem routing hints (chord: bass+other; solo: dynamic).
        # Persist a sidecar JSON for cross-endpoint access (recompute + /transcription/analyze).
        routing_hints: StemRoutingHints
        try:
            hints_raw = build_stem_routing_hints(
                stem_abs_paths, stem_classification=stem_classification
            )
            routing_hints = StemRoutingHints(**hints_raw)
            logger.info(
                "stem_routing_built job_id=%s selected=%s chord_mix=%s fallback=%s",
                job_id,
                routing_hints.selected_melodic_stem,
                routing_hints.chord_mix_stems,
                routing_hints.fallback_reason,
            )
        except DemucsEngineError as exc:
            logger.warning(
                "stem_routing_build_failed job_id=%s err=%s; using defaults",
                job_id, exc,
            )
            routing_hints = StemRoutingHints()
        try:
            (job_dir / "stem_routing.json").write_text(
                routing_hints.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            logger.exception("stem_routing_persist_failed job_id=%s", job_id)

        guitar_rel_path = stems.get("guitar")
        vocals_rel_path = stems.get("vocals")
        if not guitar_rel_path:
            # Separation contract should always return a guitar stem; fall back to stub.
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
            _set_job_analysis_stage(job_id, "chords_inferring", 0.62, "Transcribing (MT3)…")
            guitar_stem_path = backend_root / guitar_rel_path
            vocals_stem_path = backend_root / vocals_rel_path if vocals_rel_path else None
            piano_rel = stems.get("piano")
            piano_stem_path = (backend_root / piano_rel) if piano_rel else None
            analyze_start = time.time()
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
                on_stage=lambda stage, prog, label: _set_job_analysis_stage(
                    job_id, stage, prog, label
                ),
                routing_hints=routing_hints,
                stem_abs_paths=stem_abs_paths,
            )
            analyze_elapsed = time.time() - analyze_start
            logger.info("librosa analysis completed in %.2fs job_id=%s", analyze_elapsed, job_id)
        skeleton_start = time.time()
        skeleton_result = _lesson_with_skeleton_coach(result)
        skeleton_elapsed = time.time() - skeleton_start
        logger.info("skeleton coach preparation completed in %.2fs job_id=%s", skeleton_elapsed, job_id)
        
        cache_save_start = time.time()
        save_cached_lesson_for_wav(wav_path_obj, skeleton_result, player_profile=player_profile)
        cache_save_elapsed = time.time() - cache_save_start
        logger.info("lesson cache save completed in %.2fs job_id=%s", cache_save_elapsed, job_id)
        
        jobs[job_id] = JobStatus(status="complete", result=skeleton_result, error=None, analysis_stage="complete")
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)
        _set_coach_pending(job_id, len(skeleton_result.sections))
        coach_thread = threading.Thread(
            target=_hydrate_coach_copy_job,
            kwargs={"job_id": job_id, "player_profile": player_profile, "focus_area": focus_area},
            daemon=True,
        )
        coach_thread.start()
        # Commit 116: Enrich chord timeline with LLM correction (background)
        _set_chord_enrichment_pending(job_id)
        enrichment_thread = threading.Thread(
            target=_enrich_chord_timeline_job,
            kwargs={"job_id": job_id, "api_key": os.getenv("ANTHROPIC_API_KEY", "")},
            daemon=True,
        )
        enrichment_thread.start()
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
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=YOUTUBE_URL_INVALID_USER_MESSAGE,
            error_code=ANALYZE_ERROR_YOUTUBE_INVALID,
        )
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)
    except AudioTooShortError:
        logger.warning("worker failed job_id=%s audio too short", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=AUDIO_TOO_SHORT_USER_MESSAGE,
            error_code=ANALYZE_ERROR_AUDIO_TOO_SHORT,
        )
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)
    except IngestError:
        logger.exception("worker failed job_id=%s ingest error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_INGEST_FAILED,
        )
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)
    except SeparationError:
        logger.exception("worker failed job_id=%s stem separation error", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=STEM_SEPARATION_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_STEM_SEPARATION_FAILED,
        )
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)
    except Exception:
        # Fail loudly in logs; user sees a warm, safe message.
        logger.exception("worker failed job_id=%s", job_id)
        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error=ANALYSIS_FAILED_USER_MESSAGE,
            error_code=ANALYZE_ERROR_ANALYSIS_FAILED,
        )
        _persist_job_to_db(job_id)
        save_job_to_disk(job_id)


def enqueue_analyze_job(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
    player_profile: PlayerProfile | None = None,
    focus_area: CoachFocusArea | None = None,
) -> None:
    """Mark job as processing and dispatch to Celery (or fallback thread)."""
    jobs[job_id] = JobStatus(
        status="processing",
        result=None,
        error=None,
        progress=0.05,
        stage_label="Queued…",
        processing_started_at=time.time(),
        analysis_stage="initializing",
    )
    _persist_job_to_db(job_id)
    coach_hydration[job_id] = CoachHydrationStatus(status="pending", sections=[], fallback_reason=None)
    _persist_coach_to_db(job_id)
    logger.info(
        "enqueue job_id=%s status=processing youtube_url=%r upload_path=%r has_profile=%s",
        job_id,
        youtube_url,
        upload_path,
        player_profile is not None,
    )

    pp_dict = player_profile.model_dump(exclude_none=True) if player_profile else None

    # Try Celery first; fall back to daemon thread
    try:
        from app.tasks import analyze_job_task as _celery_task
        _celery_task.delay(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
            player_profile=pp_dict,
            focus_area=focus_area,
        )
        logger.info("enqueue job_id=%s dispatched to Celery", job_id)
        return
    except Exception:
        logger.info("Celery not available for job_id=%s; falling back to thread", job_id)

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


# ---- Commit 109: Beat grid recompute jobs ----------------------------------

# In-memory store for beat grid recompute job status.
recompute_jobs: dict[str, BeatGridRecomputeResponse] = {}


def get_recompute_job(job_id: str) -> BeatGridRecomputeResponse | None:
    """Get recompute job status; returns None if no recompute in progress."""
    cached = recompute_jobs.get(job_id)
    if cached is not None:
        return cached
    if _HAS_DB:
        try:
            from app.repository import get_recompute_job_status as _repo_recompute
            row = _repo_recompute(job_id)
            if row is not None:
                return BeatGridRecomputeResponse(**row)
        except Exception:
            logger.warning("Failed to read recompute from DB job_id=%s", job_id)
    return None


def _persist_coach_to_db(job_id: str) -> None:
    if not _HAS_DB:
        return
    try:
        status = coach_hydration.get(job_id)
        if status is None:
            return
        from app.repository import upsert_coach_hydration as _repo_coach
        sections = [
            s.model_dump(exclude_none=True) if hasattr(s, "model_dump") else s
            for s in (status.sections or [])
        ]
        _repo_coach(job_id, status=status.status, sections=sections, fallback_reason=status.fallback_reason)
    except Exception:
        logger.warning("Failed to persist coach hydration to DB job_id=%s (non-fatal)", job_id)


def _persist_enrichment_to_db(job_id: str) -> None:
    if not _HAS_DB:
        return
    try:
        status = chord_enrichment.get(job_id)
        if status is None:
            return
        from app.repository import upsert_chord_enrichment as _repo_enrich
        _repo_enrich(
            job_id,
            status=status.status,
            total_events=getattr(status, "total_events", None),
            corrected_events=getattr(status, "corrected_events", None),
            llm_latency_p50=getattr(status, "llm_latency_p50", None),
            llm_latency_p95=getattr(status, "llm_latency_p95", None),
            fallback_reason=status.fallback_reason,
        )
    except Exception:
        logger.warning("Failed to persist chord enrichment to DB job_id=%s (non-fatal)", job_id)


def _persist_recompute_to_db(job_id: str) -> None:
    if not _HAS_DB:
        return
    try:
        status = recompute_jobs.get(job_id)
        if status is None:
            return
        from app.repository import upsert_recompute_job as _repo_upsert_recompute
        _repo_upsert_recompute(
            job_id,
            status=status.status,
            progress=status.progress,
            stage_label=status.stage_label,
            beat_grid=status.beat_grid,
            chord_timeline=status.chord_timeline.model_dump() if status.chord_timeline else None,
            solo_notes=status.solo_notes.model_dump() if status.solo_notes else None,
            musicxml=status.musicxml,
            bar_timestamps=status.bar_timestamps,
            error=status.error,
        )
    except Exception:
        logger.warning("Failed to persist recompute to DB job_id=%s (non-fatal)", job_id)


def _set_recompute_progress(
    job_id: str,
    status: BeatGridRecomputeResponse.status,  # type: ignore[name-defined]
    *,
    progress: float | None = None,
    stage_label: str | None = None,
    beat_grid: BeatGrid | None = None,
    chord_timeline=None,
    solo_notes=None,
    musicxml: str | None = None,
    bar_timestamps: list[float] | None = None,
    error: str | None = None,
) -> None:
    """Update recompute job status."""
    recompute_jobs[job_id] = BeatGridRecomputeResponse(
        job_id=job_id,
        status=status,
        progress=progress,
        stage_label=stage_label,
        beat_grid=beat_grid if beat_grid is not None else (
            recompute_jobs[job_id].beat_grid if job_id in recompute_jobs else None
        ),
        chord_timeline=chord_timeline if chord_timeline is not None else (
            recompute_jobs[job_id].chord_timeline if job_id in recompute_jobs else None
        ),
        solo_notes=solo_notes if solo_notes is not None else (
            recompute_jobs[job_id].solo_notes if job_id in recompute_jobs else None
        ),
        musicxml=musicxml if musicxml is not None else (
            recompute_jobs[job_id].musicxml if job_id in recompute_jobs else None
        ),
        bar_timestamps=bar_timestamps if bar_timestamps is not None else (
            recompute_jobs[job_id].bar_timestamps if job_id in recompute_jobs else None
        ),
        error=error,
    )
    _persist_recompute_to_db(job_id)


def _process_beat_grid_recompute(
    job_id: str,
    *,
    time_signature: str | None,
    bpm_override: float | None,
) -> None:
    """Worker: re-derive beat grid and all dependent artifacts for an existing job."""
    from app.analyze_audio import build_lesson_json_from_librosa
    from app.beat_grid import BeatGridComputationError, estimate_beat_grid
    from app.chord_inference import infer_chords
    from app.ingest import get_data_dir, get_job_dir
    from app.musicxml_builder import build_musicxml
    from app.schemas import ChordTimeline, SoloNotes
    from app.solo_inference import infer_solo

    try:
        _set_recompute_progress(job_id, "recomputing_beats", progress=0.1, stage_label="Recomputing beat grid…")
        job = jobs.get(job_id)
        if job is None or job.result is None:
            _set_recompute_progress(job_id, "failed", error="Job not found or has no result.")
            return

        job_dir = get_job_dir(job_id)
        data_dir = get_data_dir()
        backend_root = data_dir.parent

        # Find the normalized WAV path
        wav_path = job_dir / "song.wav"
        if not wav_path.exists():
            # Try to reconstruct from stems
            _set_recompute_progress(job_id, "failed", error="Original audio not found for this job.")
            return

        # Re-estimate beat grid with overrides
        beat_grid_dict = estimate_beat_grid(
            wav_path,
            time_signature=time_signature,
            bpm_override=bpm_override,
        )
        beat_grid = BeatGrid.model_validate(beat_grid_dict)
        bar_timestamps = list(beat_grid.downbeats) if beat_grid.downbeats else [0.0]

        _set_recompute_progress(
            job_id, "recomputing_beats",
            progress=0.3,
            stage_label="Beat grid updated",
            beat_grid=beat_grid,
            bar_timestamps=bar_timestamps,
        )

        # Resolve stems for re-inference
        stems = job.result.stems or {}
        guitar_rel = stems.get("guitar")
        vocals_rel = stems.get("vocals")
        guitar_stem_path = (backend_root / guitar_rel) if guitar_rel else None
        vocals_stem_path = (backend_root / vocals_rel) if vocals_rel else None

        if guitar_stem_path is None or not guitar_stem_path.exists():
            _set_recompute_progress(job_id, "failed", error="Guitar stem not found.")
            return

        # Commit 111: Load persisted stem routing hints (sidecar). When missing,
        # fall back to defaults — preserve the previous recompute behavior
        # (full mix for chord, guitar for solo) so old jobs without sidecar
        # continue to work.
        routing_path = job_dir / "stem_routing.json"
        routing_hints: StemRoutingHints
        if routing_path.exists():
            try:
                routing_hints = StemRoutingHints.model_validate_json(
                    routing_path.read_text(encoding="utf-8")
                )
            except Exception:
                logger.exception("recompute: stem_routing read failed; using defaults")
                routing_hints = StemRoutingHints()
        else:
            routing_hints = StemRoutingHints()

        stem_abs_paths_recompute = {
            k: (backend_root / rel) for k, rel in stems.items() if rel
        }

        # Re-run chord inference with persisted routing
        _set_recompute_progress(job_id, "recomputing_chords", progress=0.4, stage_label="Recomputing chords…")
        chord_mix_path = wav_path  # default fallback = full mix
        try:
            valid_chord_stems = resolve_chord_stems(
                stem_abs_paths_recompute, routing_hints.chord_mix_stems
            )
            if len(valid_chord_stems) >= 2:
                chord_mix_path = mix_stems(valid_chord_stems, job_dir / "chord_mix.wav")
                logger.info(
                    "recompute stem_routing job_id=%s chord_mix stems=%s → %s",
                    job_id, routing_hints.chord_mix_stems, chord_mix_path,
                )
            else:
                logger.info(
                    "recompute stem_routing job_id=%s chord_fallback path=%s",
                    job_id, chord_mix_path,
                )
            chord_timeline = infer_chords(chord_mix_path, beat_grid)
        except Exception:
            logger.exception("recompute chord inference failed for job_id=%s", job_id)
            chord_timeline = ChordTimeline(events=[])

        _set_recompute_progress(
            job_id, "recomputing_chords",
            progress=0.6,
            stage_label="Chords recomputed",
            chord_timeline=chord_timeline,
        )

        # Re-run solo inference with persisted routing
        _set_recompute_progress(job_id, "recomputing_solo", progress=0.65, stage_label="Recomputing solo…")
        try:
            resolved_solo, _ = resolve_solo_stem(
                stem_abs_paths_recompute, routing_hints.selected_melodic_stem
            )
            solo_notes = infer_solo(resolved_solo, beat_grid)
            logger.info(
                "recompute stem_routing job_id=%s solo_stem=%s",
                job_id, resolved_solo,
            )
        except Exception:
            logger.exception("recompute solo inference failed for job_id=%s", job_id)
            solo_notes = SoloNotes(notes=[])

        _set_recompute_progress(
            job_id, "recomputing_solo",
            progress=0.8,
            stage_label="Solo recomputed",
            solo_notes=solo_notes,
        )

        # Rebuild MusicXML
        _set_recompute_progress(job_id, "rebuilding_musicxml", progress=0.85, stage_label="Rebuilding MusicXML…")
        musicxml_str = ""
        try:
            if chord_timeline and solo_notes and beat_grid:
                musicxml_str = build_musicxml(
                    beat_grid=beat_grid,
                    chord_timeline=chord_timeline,
                    solo_notes=solo_notes,
                    title=job.result.song_title or "Harmoniq Score",
                    artist=job.result.artist or "Harmoniq AI",
                    key_signature=job.result.key,
                )
        except Exception:
            logger.exception("recompute MusicXML build failed for job_id=%s", job_id)

        # Update the main job result with new artifacts
        patched = job.result.model_copy(update={
            "beat_grid_structured": beat_grid,
            "beat_grid": beat_grid.beats,
            "bar_timestamps": bar_timestamps,
            "chord_timeline": chord_timeline,
            "solo_notes": solo_notes,
            "musicxml": musicxml_str,
        })
        jobs[job_id] = JobStatus(
            status=job.status,
            result=patched,
            error=job.error,
            error_code=job.error_code,
            progress=job.progress,
            stage_label=job.stage_label,
            processing_started_at=job.processing_started_at,
            analysis_stage=job.analysis_stage,
        )

        # Persist recompute artifacts to disk so they survive server restarts
        try:
            from pathlib import Path as _Path
            job_dir = get_job_dir(job_id)
            (job_dir / "BeatGrid.json").write_text(
                beat_grid.model_dump_json(indent=2), encoding="utf-8"
            )
            if chord_timeline:
                (job_dir / "chordTimeline.json").write_text(
                    chord_timeline.model_dump_json(indent=2), encoding="utf-8"
                )
            if solo_notes:
                (job_dir / "SoloNotes.json").write_text(
                    solo_notes.model_dump_json(indent=2), encoding="utf-8"
                )
            if musicxml_str:
                (job_dir / "score.musicxml").write_text(musicxml_str, encoding="utf-8")
            logger.info("recompute artifacts persisted to disk for job_id=%s", job_id)
        except Exception:
            logger.exception("Failed to persist recompute artifacts for job_id=%s", job_id)

        _set_recompute_progress(
            job_id, "complete",
            progress=1.0,
            stage_label="Recompute complete",
            beat_grid=beat_grid,
            chord_timeline=chord_timeline,
            solo_notes=solo_notes,
            musicxml=musicxml_str,
            bar_timestamps=bar_timestamps,
        )
        logger.info("beat grid recompute complete job_id=%s", job_id)

    except BeatGridComputationError as exc:
        logger.warning("beat grid recompute failed for job_id=%s: %s", job_id, exc)
        _set_recompute_progress(job_id, "failed", error=str(exc))
    except Exception:
        logger.exception("beat grid recompute failed for job_id=%s", job_id)
        _set_recompute_progress(job_id, "failed", error="Recompute failed unexpectedly.")


def enqueue_beat_grid_recompute(
    job_id: str,
    *,
    time_signature: str | None,
    bpm_override: float | None,
) -> None:
    """Dispatch beat grid recompute to Celery (or fallback thread)."""
    _set_recompute_progress(job_id, "pending", progress=0.0, stage_label="Queued…")
    try:
        from app.tasks import beat_grid_recompute_task as _celery_task
        _celery_task.delay(
            job_id,
            time_signature=time_signature,
            bpm_override=bpm_override,
        )
        logger.info("recompute job_id=%s dispatched to Celery", job_id)
        return
    except Exception:
        logger.info("Celery not available for recompute job_id=%s; falling back to thread", job_id)

    t = threading.Thread(
        target=_process_beat_grid_recompute,
        kwargs={"job_id": job_id, "time_signature": time_signature, "bpm_override": bpm_override},
        daemon=True,
    )
    t.start()

