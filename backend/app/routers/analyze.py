"""Harmoniq analyze & transcription router — job creation, status polling, coach hydration, SSE."""

from __future__ import annotations

import asyncio
import datetime
import inspect
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.audio_processing import AudioPreparationError, prepare_audio_input
from app.beat_grid import (
    BeatGridComputationError,
    dependent_artifacts_for_grid_override,
    estimate_beat_grid,
)
from app.chord_inference import infer_chords
from app.demucs_engine import DemucsEngineError, build_stem_routing_hints, separate_with_demucs
from app.pipeline_proof import YouTubeDownloadError
from app.ingest import AUDIO_TOO_SHORT_USER_MESSAGE, MIN_ANALYZE_DURATION_SECONDS, get_job_dir, wav_file_duration_seconds
from app.jobs import (
    ANALYSIS_FAILED_USER_MESSAGE,
    ANALYZE_ERROR_ANALYSIS_FAILED,
    enqueue_analyze_job,
    enqueue_beat_grid_recompute,
    get_chord_enrichment,
    get_coach_hydration,
    get_recompute_job,
    jobs,
    save_job_to_disk,
)
from app.schemas import (
    AnalyzeJobCreated,
    AnalyzeTranscriptionResponse,
    BeatGrid,
    BeatGridRecomputeRequest,
    BeatGridRecomputeResponse,
    ChordCorrectionRequest,
    ChordEnrichmentStatus,
    ChordEvent,
    ChordTimeline,
    CoachHydrationStatus,
    ContributeRequest,
    ContributeResponse,
    CorrectionExportRequest,
    CorrectionHistory,
    CorrectionRecord,
    CorrectionRevertRequest,
    JobStatus,
    SoloNote,
    SoloNoteCorrectionRequest,
    SoloNotes,
    TranscriptionPrepareResponse,
    TranscriptionVerifyRequest,
    TranscriptionVerifyResponse,
    VoicingOverrideRequest,
)
from app.solo_inference import infer_solo
from app.sse import sse_response

logger = logging.getLogger("harmoniq.api.analyze")

router = APIRouter(tags=["Analyze"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

ALLOWED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/ogg",
    "audio/webm",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
}


class UploadTooLargeError(ValueError):
    pass


class UnsupportedMimeTypeError(ValueError):
    pass


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_player_profile_field(raw: object) -> PlayerProfile | None:
    """Accept JSON object or JSON string; invalid payloads are dropped."""
    if raw is None:
        return None
    data: object
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            logger.warning("player_profile JSON decode failed; ignoring")
            return None
    elif isinstance(raw, dict):
        data = raw
    else:
        logger.warning("player_profile unsupported type=%s; ignoring", type(raw).__name__)
        return None
    if not isinstance(data, dict):
        return None
    from app.schemas import PlayerProfile
    try:
        return PlayerProfile.model_validate(data)
    except Exception:
        logger.warning("player_profile validation failed; ignoring")
        return None


def _coerce_optional_float(raw: object, *, field: str) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        txt = raw.strip()
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{field} must be numeric.") from exc
    raise HTTPException(status_code=422, detail=f"{field} must be numeric.")


async def _save_uploadfile_limited(
    upload: UploadFile,
    dest_path: Path,
    *,
    max_bytes: int,
    chunk_bytes: int = 1024 * 1024,
) -> None:
    content_type = upload.content_type or ""
    if content_type and content_type.lower() not in ALLOWED_AUDIO_MIME_TYPES:
        raise UnsupportedMimeTypeError(f"Unsupported MIME type: {content_type}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest_path.open("wb") as f:
        while True:
            chunk = await upload.read(chunk_bytes)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UploadTooLargeError(f"Upload exceeds max_bytes={max_bytes}")
            f.write(chunk)


def _run_transcription_prepare_pipeline(
    *,
    job_id: str,
    youtube_url: str | None,
    upload_path: str | None,
    time_signature_override: str | None,
    bpm_override: float | None,
) -> TranscriptionPrepareResponse:
    prepared = prepare_audio_input(
        job_id,
        youtube_url=youtube_url,
        upload_path=upload_path,
    )
    stems = separate_with_demucs(prepared.normalized_wav_path, prepared.job_dir)
    beat_grid_payload = estimate_beat_grid(
        prepared.normalized_wav_path,
        time_signature=time_signature_override,
        bpm_override=bpm_override,
    )
    backend_root = _backend_root().resolve()
    stem_abs_paths: dict[str, Path] = {}
    for key, rel in stems.items():
        p = Path(rel)
        stem_abs_paths[key] = p if p.is_absolute() else backend_root / rel
    stem_routing = build_stem_routing_hints(stem_abs_paths)
    invalidated: list[str] = []
    if time_signature_override is not None or bpm_override is not None:
        invalidated = dependent_artifacts_for_grid_override()
    def _rel_or_abs(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(backend_root).as_posix())
        except ValueError:
            return str(p.resolve().as_posix())
    audio_chunk_paths = [_rel_or_abs(p) for p in prepared.chunk_paths]
    return TranscriptionPrepareResponse(
        job_id=job_id,
        stems=stems,
        beat_grid=BeatGrid.model_validate(beat_grid_payload),
        stem_routing=stem_routing,
        audio_chunk_paths=audio_chunk_paths,
        invalidated_artifacts=invalidated,
    )


@router.post(
    "/transcription/prepare",
    response_model=TranscriptionPrepareResponse,
    summary="POST /transcription/prepare — stems + BeatGrid",
)
async def transcription_prepare(request: Request) -> TranscriptionPrepareResponse:
    job_id = str(uuid.uuid4())
    youtube_url: str | None = None
    upload_path: str | None = None
    time_signature_override: str | None = None
    bpm_override: float | None = None
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        youtube_url = str(form.get("youtube_url") or form.get("url") or "").strip() or None
        time_signature_override = str(form.get("time_signature_override") or "").strip() or None
        bpm_override = _coerce_optional_float(form.get("bpm_override"), field="bpm_override")
        if upload is not None:
            suffix = Path(upload.filename or "").suffix or ".audio"
            job_dir = get_job_dir(job_id)
            dest = job_dir / f"input{suffix}"
            if isinstance(upload, UploadFile):
                await _save_uploadfile_limited(upload, dest, max_bytes=MAX_UPLOAD_BYTES)
            elif isinstance(upload, (bytes, bytearray)):
                if len(upload) > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=400, detail="Upload exceeds max allowed size.")
                dest.write_bytes(bytes(upload))
            elif hasattr(upload, "read"):
                raw = upload.read()
                if inspect.isawaitable(raw):
                    raw = await raw
                if isinstance(raw, str):
                    raw = raw.encode()
                if not isinstance(raw, (bytes, bytearray)):
                    raise HTTPException(status_code=400, detail="Multipart file must be bytes-like.")
                if len(raw) > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=400, detail="Upload exceeds max allowed size.")
                dest.write_bytes(bytes(raw))
            else:
                raise HTTPException(status_code=400, detail="Multipart file must be UploadFile or bytes-like.")
            upload_path = str(dest)
    else:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object payload.")
        youtube_url = str(body.get("youtube_url") or body.get("url") or "").strip() or None
        time_signature_override = str(body.get("time_signature_override") or "").strip() or None
        bpm_override = _coerce_optional_float(body.get("bpm_override"), field="bpm_override")
    if not youtube_url and not upload_path:
        raise HTTPException(status_code=400, detail="Provide either `file` upload or `youtube_url`.")
    try:
        return await asyncio.to_thread(
            _run_transcription_prepare_pipeline,
            job_id=job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
            time_signature_override=time_signature_override,
            bpm_override=bpm_override,
        )
    except HTTPException:
        raise
    except UploadTooLargeError:
        raise HTTPException(status_code=413, detail="Upload exceeds max allowed size (50MB).") from None
    except UnsupportedMimeTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    except YouTubeDownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (AudioPreparationError, DemucsEngineError, BeatGridComputationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("POST /transcription/prepare failed job_id=%s", job_id)
        raise HTTPException(status_code=500, detail="Transcription preparation failed unexpectedly.") from None


@router.post(
    "/analyze",
    response_model=AnalyzeJobCreated,
    summary="POST /analyze (async — returns job_id immediately)",
)
async def analyze(request: Request) -> AnalyzeJobCreated:
    job_id = str(uuid.uuid4())
    youtube_url: str | None = None
    upload_path: str | None = None
    player_profile: object = None
    focus_area: str | None = None
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            youtube_url = form.get("youtube_url") or form.get("url")
            player_profile = _parse_player_profile_field(form.get("player_profile"))
            focus_area = form.get("focus_area")
            if upload is not None:
                suffix = Path(upload.filename or "").suffix or ".audio"
                job_dir = get_job_dir(job_id)
                dest = job_dir / f"input{suffix}"
                if isinstance(upload, UploadFile):
                    await _save_uploadfile_limited(upload, dest, max_bytes=MAX_UPLOAD_BYTES)
                elif isinstance(upload, (bytes, bytearray)):
                    if len(upload) > MAX_UPLOAD_BYTES:
                        raise UploadTooLargeError(f"Upload exceeds max_bytes={MAX_UPLOAD_BYTES}")
                    dest.write_bytes(bytes(upload))
                elif hasattr(upload, "read"):
                    raw = upload.read()
                    if inspect.isawaitable(raw):
                        raw = await raw
                    if isinstance(raw, str):
                        raw = raw.encode()
                    if not isinstance(raw, (bytes, bytearray)):
                        raise TypeError("Multipart file must be bytes-like")
                    if len(raw) > MAX_UPLOAD_BYTES:
                        raise UploadTooLargeError(f"Upload exceeds max_bytes={MAX_UPLOAD_BYTES}")
                    dest.write_bytes(bytes(raw))
                else:
                    raise TypeError("Expected multipart 'file' to be UploadFile or bytes-like")
                upload_path = str(dest)
                pre_dur = wav_file_duration_seconds(dest)
                if pre_dur is not None and pre_dur < MIN_ANALYZE_DURATION_SECONDS:
                    raise HTTPException(status_code=400, detail=AUDIO_TOO_SHORT_USER_MESSAGE)
        else:
            body = await request.json()
            if isinstance(body, dict):
                youtube_url = body.get("url") or body.get("youtube_url")
                player_profile = _parse_player_profile_field(body.get("player_profile"))
                focus_area = body.get("focus_area")
    except HTTPException:
        raise
    except UploadTooLargeError:
        logger.warning("POST /analyze upload too large job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE, error_code=ANALYZE_ERROR_ANALYSIS_FAILED)
        return AnalyzeJobCreated(job_id=job_id)
    except UnsupportedMimeTypeError:
        logger.warning("POST /analyze unsupported MIME type job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error="Unsupported file type. Please upload an audio file (MP3, WAV, OGG, WEBM, M4A).", error_code=ANALYZE_ERROR_ANALYSIS_FAILED)
        return AnalyzeJobCreated(job_id=job_id)
    except Exception:
        logger.exception("POST /analyze failed to parse input job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE, error_code=ANALYZE_ERROR_ANALYSIS_FAILED)
        return AnalyzeJobCreated(job_id=job_id)
    logger.info("POST /analyze created job_id=%s status=processing youtube_url=%r upload_path=%r", job_id, youtube_url, upload_path)
    enqueue_analyze_job(job_id=job_id, youtube_url=youtube_url, upload_path=upload_path, player_profile=player_profile, focus_area=focus_area)
    return AnalyzeJobCreated(job_id=job_id)


@router.get(
    "/analyze/{job_id}",
    response_model=JobStatus,
    summary="GET /analyze/{job_id}",
)
async def analyze_status(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.info("GET /analyze/%s — job not yet in store, returning queued", job_id)
        return JobStatus(status="queued", result=None, error=None, error_code=None)
    logger.info("GET /analyze/%s status=%s", job_id, job.status)
    return job


@router.get(
    "/analyze/{job_id}/stream",
    summary="GET /analyze/{job_id}/stream — SSE progress stream",
)
async def analyze_stream(job_id: str):
    """Stream real-time progress events for an analysis job via Server-Sent Events."""
    return sse_response(job_id)


@router.get(
    "/analyze/{job_id}/coach",
    response_model=CoachHydrationStatus,
    summary="GET /analyze/{job_id}/coach — coach hydration status",
)
async def analyze_coach_status(job_id: str) -> CoachHydrationStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.warning("GET /analyze/%s/coach — unknown job_id (404)", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    status = get_coach_hydration(job_id)
    if status is None:
        return CoachHydrationStatus(status="pending", sections=[], fallback_reason=None)
    return status


@router.post("/transcription/analyze/{job_id}", response_model=AnalyzeTranscriptionResponse)
async def analyze_transcription(job_id: str):
    job_dir = Path(f"./data/jobs/{job_id}")
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found. Run prepare first.")
    grid_path = job_dir / "BeatGrid.json"
    if not grid_path.exists():
        raise HTTPException(status_code=400, detail="BeatGrid missing. Run prepare first.")
    with open(grid_path) as f:
        beat_grid = BeatGrid.model_validate_json(f.read())
    stems_dir = job_dir / "stems"
    chord_mix_path = stems_dir / "other.wav"
    melodic_stem_path = stems_dir / "guitar.wav"
    if not chord_mix_path.exists() or not melodic_stem_path.exists():
        raise HTTPException(status_code=400, detail="Required stems missing.")
    chord_timeline, _chord_metrics = infer_chords(chord_mix_path, beat_grid)
    solo_notes = infer_solo(melodic_stem_path, beat_grid)
    with open(job_dir / "chordTimeline.json", "w") as f:
        f.write(chord_timeline.model_dump_json(indent=2))
    with open(job_dir / "SoloNotes.json", "w") as f:
        f.write(solo_notes.model_dump_json(indent=2))
    return AnalyzeTranscriptionResponse(job_id=job_id, chord_timeline=chord_timeline, solo_notes=solo_notes)


@router.post(
    "/transcription/verify",
    response_model=TranscriptionVerifyResponse,
    summary="POST /transcription/verify — user corrections for low-confidence transcriptions",
)
async def verify_transcription(req: TranscriptionVerifyRequest):
    if os.getenv("HARMONIQ_SKIP_TRANSCRIPTION_VERIFY") == "1":
        return TranscriptionVerifyResponse(success=True, message="Verification bypassed (HARMONIQ_SKIP_TRANSCRIPTION_VERIFY=1)", corrections_applied=False)
    job_dir = Path(f"./data/jobs/{req.job_id}")
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job {req.job_id} not found.")
    lesson_path = job_dir / "lesson.json"
    if not lesson_path.exists():
        raise HTTPException(status_code=404, detail="Lesson data not found for this job.")
    with open(lesson_path) as f:
        lesson_data = json.load(f)
    corrections_applied = False
    if req.stem_routing_override:
        if "stems" in lesson_data:
            if "transcription_metadata" not in lesson_data:
                lesson_data["transcription_metadata"] = {}
            lesson_data["transcription_metadata"]["stem_routing_override"] = req.stem_routing_override
            corrections_applied = True
    if req.user_confirmed:
        if "transcription_metadata" not in lesson_data:
            lesson_data["transcription_metadata"] = {}
        lesson_data["transcription_metadata"]["user_confirmed"] = True
        lesson_data["transcription_metadata"]["user_confirmed_at"] = datetime.datetime.now().isoformat()
        corrections_applied = True
    if req.user_notes:
        if "transcription_metadata" not in lesson_data:
            lesson_data["transcription_metadata"] = {}
        lesson_data["transcription_metadata"]["user_notes"] = req.user_notes
        corrections_applied = True
    if corrections_applied:
        with open(lesson_path, "w") as f:
            json.dump(lesson_data, f, indent=2)
    return TranscriptionVerifyResponse(success=True, message="Corrections recorded successfully" if corrections_applied else "No corrections to apply", corrections_applied=corrections_applied)


# ---------------------------------------------------------------------------
# Commit 109: Beat grid recompute endpoints (async)
# ---------------------------------------------------------------------------

@router.post(
    "/analyze/{job_id}/beat-grid/recompute",
    response_model=BeatGridRecomputeResponse,
    summary="POST /analyze/{job_id}/beat-grid/recompute — async recompute with overrides",
)
async def beat_grid_recompute(job_id: str, req: BeatGridRecomputeRequest) -> BeatGridRecomputeResponse:
    """Trigger asynchronous recomputation of beat grid and all dependent artifacts.

    Poll GET /analyze/{job_id}/beat-grid/recompute for status updates.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    enqueue_beat_grid_recompute(
        job_id,
        time_signature=req.time_signature,
        bpm_override=req.bpm_override,
    )
    return BeatGridRecomputeResponse(
        job_id=job_id,
        status="pending",
        progress=0.0,
        stage_label="Queued…",
    )


@router.get(
    "/analyze/{job_id}/beat-grid/recompute",
    response_model=BeatGridRecomputeResponse,
    summary="GET /analyze/{job_id}/beat-grid/recompute — poll recompute status",
)
async def beat_grid_recompute_status(job_id: str) -> BeatGridRecomputeResponse:
    """Poll recompute job status. Returns 404 if no recompute has been triggered."""
    status = get_recompute_job(job_id)
    if status is None:
        try:
            from app.repository import get_recompute_job_status as _repo_recompute
            db_status = _repo_recompute(job_id)
            if db_status is not None:
                from app.schemas import BeatGridRecomputeResponse as _BGR
                return _BGR(**db_status)
        except Exception:
            logger.exception("GET /analyze/%s/beat-grid/recompute — DB fallback failed", job_id)
        raise HTTPException(status_code=404, detail=f"No recompute job for {job_id}.")
    return status


@router.get(
    "/analyze/{job_id}/chord-enrichment",
    response_model=ChordEnrichmentStatus,
    summary="GET /analyze/{job_id}/chord-enrichment — chord enrichment status (commit 116)",
)
async def analyze_chord_enrichment_status(job_id: str) -> ChordEnrichmentStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.warning("GET /analyze/%s/chord-enrichment — unknown job_id (404)", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    status = get_chord_enrichment(job_id)
    if status is None:
        try:
            from app.repository import get_chord_enrichment_status as _repo_enrich
            db_status = _repo_enrich(job_id)
            if db_status is not None:
                return db_status
        except Exception:
            logger.exception("GET /analyze/%s/chord-enrichment — DB fallback failed", job_id)
        return ChordEnrichmentStatus(status="pending")
    return status




# ---------------------------------------------------------------------------
# Commit 109: Analysis Correction Endpoints
# ---------------------------------------------------------------------------

def _load_job_artifacts(job_id: str) -> tuple[BeatGrid | None, ChordTimeline | None, SoloNotes | None]:
    """Load persisted artifacts from disk for a job."""
    job_dir = get_job_dir(job_id)
    beat_grid = None
    chord_timeline = None
    solo_notes = None

    bg_path = job_dir / "BeatGrid.json"
    if bg_path.exists():
        with open(bg_path) as f:
            beat_grid = BeatGrid.model_validate_json(f.read())

    ct_path = job_dir / "chordTimeline.json"
    if ct_path.exists():
        with open(ct_path) as f:
            chord_timeline = ChordTimeline.model_validate_json(f.read())

    sn_path = job_dir / "SoloNotes.json"
    if sn_path.exists():
        with open(sn_path) as f:
            solo_notes = SoloNotes.model_validate_json(f.read())

    return beat_grid, chord_timeline, solo_notes


def _save_job_artifacts(job_id: str, *, chord_timeline: ChordTimeline | None = None, solo_notes: SoloNotes | None = None) -> None:
    """Save updated artifacts back to disk."""
    job_dir = get_job_dir(job_id)
    if chord_timeline is not None:
        with open(job_dir / "chordTimeline.json", "w") as f:
            f.write(chord_timeline.model_dump_json(indent=2))
    if solo_notes is not None:
        with open(job_dir / "SoloNotes.json", "w") as f:
            f.write(solo_notes.model_dump_json(indent=2))


def _load_correction_history(job_id: str) -> list[dict]:
    """Load correction history from disk."""
    job_dir = get_job_dir(job_id)
    history_path = job_dir / "corrections.json"
    if history_path.exists():
        with open(history_path) as f:
            return json.load(f)
    return []


def _save_correction_history(job_id: str, corrections: list[dict]) -> None:
    """Save correction history to disk."""
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    with open(job_dir / "corrections.json", "w") as f:
        json.dump(corrections, f, indent=2)


def _rebuild_score_for_job(job_id: str) -> None:
    """Rebuild lesson- and section-level MusicXML from the corrected artifacts (Commit 153).

    Called at the end of every correction mutation (PATCH + revert) so that the
    frontend's debounced re-fetch of GET /analyze/{job_id} serves a fresh score
    instead of the load-time copy. Mirrors the beat-grid recompute rebuild in
    jobs.py: artifacts are already saved when this runs.
    """
    from app.analyze_audio import _filter_chord_timeline_by_section, _filter_solo_notes_by_section
    from app.musicxml_builder import build_musicxml

    job = jobs.get(job_id)
    if job is None or job.result is None:
        logger.warning("score rebuild skipped job_id=%s: no job result", job_id)
        return

    beat_grid, chord_timeline, solo_notes = _load_job_artifacts(job_id)
    if beat_grid is None or chord_timeline is None or solo_notes is None:
        logger.warning("score rebuild skipped job_id=%s: artifacts missing", job_id)
        return

    lesson = job.result
    title = lesson.song_title or "Harmoniq Score"
    artist = lesson.artist or "Harmoniq AI"

    musicxml_str = build_musicxml(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        title=title,
        artist=artist,
        key_signature=lesson.key,
    )

    # Per-section rebuild — SessionStemAndTab prefers section.musicxml over the
    # lesson-level score, so a lesson-only rebuild would still render stale.
    rebuilt_sections = []
    for section in lesson.sections:
        section_chords = _filter_chord_timeline_by_section(
            chord_timeline, section.start_time_seconds, section.end_time_seconds
        )
        section_notes = _filter_solo_notes_by_section(
            solo_notes, section.start_time_seconds, section.end_time_seconds
        )
        updates: dict = {}
        if section_chords.events:
            updates["chord_timeline"] = section_chords.model_dump()
        if section_notes.notes:
            updates["solo_notes"] = section_notes.model_dump()
        if section.musicxml and section_chords.events and section_notes.notes:
            updates["musicxml"] = build_musicxml(
                beat_grid=beat_grid,
                chord_timeline=section_chords,
                solo_notes=section_notes,
                title=title,
                artist=artist,
                key_signature=lesson.key,
            )
        rebuilt_sections.append(section.model_copy(update=updates) if updates else section)

    jobs[job_id] = job.model_copy(
        update={
            "result": lesson.model_copy(
                update={
                    "chord_timeline": chord_timeline,
                    "solo_notes": solo_notes,
                    "musicxml": musicxml_str,
                    "sections": rebuilt_sections,
                }
            )
        }
    )

    try:
        (get_job_dir(job_id) / "score.musicxml").write_text(musicxml_str, encoding="utf-8")
    except OSError:
        logger.exception("score.musicxml persist failed job_id=%s", job_id)

    save_job_to_disk(job_id)
    logger.info("score rebuilt after correction job_id=%s length=%d", job_id, len(musicxml_str))


@router.patch(
    "/analyze/{job_id}/chord/{beat_index}",
    response_model=CorrectionRecord,
    summary="PATCH /analyze/{job_id}/chord/{beat_index} — correct a chord symbol",
)
async def correct_chord(job_id: str, beat_index: int, req: ChordCorrectionRequest) -> CorrectionRecord:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    _, chord_timeline, _ = _load_job_artifacts(job_id)
    if chord_timeline is None or beat_index < 0 or beat_index >= len(chord_timeline.events):
        raise HTTPException(status_code=400, detail=f"Invalid beat_index {beat_index} for job {job_id}")

    original = chord_timeline.events[beat_index]
    record = CorrectionRecord(
        correction_type="chord",
        index=beat_index,
        original_value={"chord": original.chord, "confidence": original.confidence, "timestamp": original.timestamp},
        corrected_value={"chord": req.chord},
        reason=req.reason,
        applied_at=datetime.datetime.now().isoformat(),
    )

    chord_timeline.events[beat_index] = ChordEvent(
        timestamp=original.timestamp,
        chord=req.chord,
        confidence=1.0,
    )
    _save_job_artifacts(job_id, chord_timeline=chord_timeline)

    history = _load_correction_history(job_id)
    history.append(record.model_dump())
    _save_correction_history(job_id, history)

    _rebuild_score_for_job(job_id)
    return record


@router.patch(
    "/analyze/{job_id}/solo-note/{note_index}",
    response_model=CorrectionRecord,
    summary="PATCH /analyze/{job_id}/solo-note/{note_index} — correct a solo note",
)
async def correct_solo_note(job_id: str, note_index: int, req: SoloNoteCorrectionRequest) -> CorrectionRecord:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    _, _, solo_notes = _load_job_artifacts(job_id)
    if solo_notes is None or note_index < 0 or note_index >= len(solo_notes.notes):
        raise HTTPException(status_code=400, detail=f"Invalid note_index {note_index} for job {job_id}")

    original = solo_notes.notes[note_index]
    original_dict = original.model_dump()

    corrected_dict: dict[str, Any] = {}
    if req.pitch is not None:
        corrected_dict["pitch"] = req.pitch
    if req.start_time is not None:
        corrected_dict["start_time"] = req.start_time
    if req.duration is not None:
        corrected_dict["duration"] = req.duration
    if req.velocity is not None:
        corrected_dict["velocity"] = req.velocity
    if req.string is not None:
        corrected_dict["string"] = req.string
    if req.fret is not None:
        corrected_dict["fret"] = req.fret

    record = CorrectionRecord(
        correction_type="solo_note",
        index=note_index,
        original_value=original_dict,
        corrected_value=corrected_dict,
        reason=req.reason,
        applied_at=datetime.datetime.now().isoformat(),
    )

    solo_notes.notes[note_index] = SoloNote(
        pitch=req.pitch if req.pitch is not None else original.pitch,
        start_time=req.start_time if req.start_time is not None else original.start_time,
        duration=req.duration if req.duration is not None else original.duration,
        velocity=req.velocity if req.velocity is not None else original.velocity,
    )
    _save_job_artifacts(job_id, solo_notes=solo_notes)

    history = _load_correction_history(job_id)
    history.append(record.model_dump())
    _save_correction_history(job_id, history)

    _rebuild_score_for_job(job_id)
    return record


@router.patch(
    "/analyze/{job_id}/chord/{beat_index}/voicing",
    response_model=CorrectionRecord,
    summary="PATCH /analyze/{job_id}/chord/{beat_index}/voicing — override CAGED voicing shape",
)
async def override_voicing(job_id: str, beat_index: int, req: VoicingOverrideRequest) -> CorrectionRecord:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    _, chord_timeline, _ = _load_job_artifacts(job_id)
    if chord_timeline is None or beat_index < 0 or beat_index >= len(chord_timeline.events):
        raise HTTPException(status_code=400, detail=f"Invalid beat_index {beat_index} for job {job_id}")

    original = chord_timeline.events[beat_index]
    record = CorrectionRecord(
        correction_type="voicing",
        index=beat_index,
        original_value={"chord": original.chord, "voicing_shape": original.voicing_shape},
        corrected_value={"chord": original.chord, "voicing_shape": req.voicing_shape},
        reason=req.reason,
        applied_at=datetime.datetime.now().isoformat(),
    )

    chord_timeline.events[beat_index] = ChordEvent(
        timestamp=original.timestamp,
        chord=original.chord,
        confidence=original.confidence,
        voicing_shape=req.voicing_shape,
        voicing_position=original.voicing_position,
    )
    _save_job_artifacts(job_id, chord_timeline=chord_timeline)

    history = _load_correction_history(job_id)
    history.append(record.model_dump())
    _save_correction_history(job_id, history)

    _rebuild_score_for_job(job_id)
    return record


@router.get(
    "/analyze/{job_id}/corrections",
    response_model=CorrectionHistory,
    summary="GET /analyze/{job_id}/corrections — correction history",
)
async def get_correction_history(job_id: str) -> CorrectionHistory:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    history = _load_correction_history(job_id)
    corrections = [CorrectionRecord(**c) for c in history]

    _, chord_timeline, solo_notes = _load_job_artifacts(job_id)
    total_predicted = 0
    if chord_timeline:
        total_predicted += len(chord_timeline.events)
    if solo_notes:
        total_predicted += len(solo_notes.notes)

    coverage = len(corrections) / total_predicted if total_predicted > 0 else 0.0

    return CorrectionHistory(
        job_id=job_id,
        corrections=corrections,
        correction_count=len(corrections),
        correction_coverage=round(coverage, 4),
    )


@router.post(
    "/analyze/{job_id}/corrections/revert",
    response_model=CorrectionRecord,
    summary="POST /analyze/{job_id}/corrections/revert — revert a specific correction",
)
async def revert_correction(job_id: str, req: CorrectionRevertRequest) -> CorrectionRecord:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    history = _load_correction_history(job_id)
    if req.correction_index < 0 or req.correction_index >= len(history):
        raise HTTPException(status_code=400, detail=f"Invalid correction_index {req.correction_index}")

    correction = history[req.correction_index]
    corr_type = correction.get("correction_type")
    index = correction.get("index", 0)
    original_value = correction.get("original_value", {})

    if corr_type == "chord":
        _, chord_timeline, _ = _load_job_artifacts(job_id)
        if chord_timeline and 0 <= index < len(chord_timeline.events):
            chord_timeline.events[index] = ChordEvent(
                timestamp=chord_timeline.events[index].timestamp,
                chord=original_value.get("chord", "N"),
                confidence=original_value.get("confidence", 1.0),
            )
            _save_job_artifacts(job_id, chord_timeline=chord_timeline)
    elif corr_type == "solo_note":
        _, _, solo_notes = _load_job_artifacts(job_id)
        if solo_notes and 0 <= index < len(solo_notes.notes):
            solo_notes.notes[index] = SoloNote(
                pitch=original_value.get("pitch", 60),
                start_time=original_value.get("start_time", 0.0),
                duration=original_value.get("duration", 0.5),
                velocity=original_value.get("velocity", 80),
            )
            _save_job_artifacts(job_id, solo_notes=solo_notes)
    elif corr_type == "voicing":
        _, chord_timeline, _ = _load_job_artifacts(job_id)
        if chord_timeline and 0 <= index < len(chord_timeline.events):
            event = chord_timeline.events[index]
            chord_timeline.events[index] = ChordEvent(
                timestamp=event.timestamp,
                chord=event.chord,
                confidence=event.confidence,
                voicing_shape=original_value.get("voicing_shape"),
                voicing_position=event.voicing_position,
            )
            _save_job_artifacts(job_id, chord_timeline=chord_timeline)

    history.pop(req.correction_index)
    _save_correction_history(job_id, history)

    _rebuild_score_for_job(job_id)
    return CorrectionRecord(**correction)


@router.post(
    "/analyze/{job_id}/corrections/export",
    summary="POST /analyze/{job_id}/corrections/export — export corrections as training data",
)
async def export_corrections(job_id: str, req: CorrectionExportRequest) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    history = _load_correction_history(job_id)
    filtered = [
        c for c in history
        if (req.include_solo_notes and c.get("correction_type") == "solo_note")
        or (req.include_voicings and c.get("correction_type") == "voicing")
        or c.get("correction_type") == "chord"
    ]

    if req.format == "csv":
        import csv
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["correction_type", "index", "original_value", "corrected_value", "reason", "applied_at"])
        writer.writeheader()
        writer.writerows(filtered)
        return {"format": "csv", "data": buf.getvalue(), "count": len(filtered)}

    return {"format": "json", "data": filtered, "count": len(filtered)}


@router.post(
    "/analyze/{job_id}/contribute",
    response_model=ContributeResponse,
    summary="POST /analyze/{job_id}/contribute — contribute corrected audio to training",
)
async def contribute_to_training(job_id: str, req: ContributeRequest) -> ContributeResponse:
    """Contribute the current (corrected) chord timeline to training data."""
    from app.contribute import ContributionError, contribute_audio

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if job.result is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} has no result yet.")
    lesson = job.result

    if not lesson.chord_timeline or not lesson.chord_timeline.events:
        raise HTTPException(status_code=400, detail="No chord timeline available to contribute.")

    try:
        result = contribute_audio(
            job_id=job_id,
            timeline=lesson.chord_timeline,
            contributor_id=req.contributor_id,
            license=req.license,
        )
    except ContributionError as e:
        raise HTTPException(status_code=400, detail={"error": e.args[0], "message": e.args[1]})

    return ContributeResponse(**result)
