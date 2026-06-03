"""Harmoniq analyze & transcription router — job creation, status polling, coach hydration."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile

from app.audio_processing import AudioPreparationError, prepare_audio_input
from app.audio_mix import mix_stems, resolve_chord_stems, resolve_solo_stem
from app.beat_grid import (
    BeatGridComputationError,
    dependent_artifacts_for_grid_override,
    estimate_beat_grid,
)
from app.chord_inference import infer_chords
from app.demucs_engine import DemucsEngineError, build_stem_routing_hints, separate_with_demucs
from app.ingest import AUDIO_TOO_SHORT_USER_MESSAGE, MIN_ANALYZE_DURATION_SECONDS, get_job_dir, wav_file_duration_seconds
from app.jobs import (
    ANALYSIS_FAILED_USER_MESSAGE,
    ANALYZE_ERROR_ANALYSIS_FAILED,
    enqueue_analyze_job,
    enqueue_beat_grid_recompute,
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
    ChordCorrectionResponse,
    CoachHydrationStatus,
    CorrectionExportResponse,
    CorrectionHistoryItem,
    CorrectionHistoryResponse,
    JobStatus,
    NoteCorrectionRequest,
    NoteCorrectionResponse,
    StemRoutingHints,
    TranscriptionPrepareResponse,
    TranscriptionVerifyRequest,
    TranscriptionVerifyResponse,
    VoicingOverrideRequest,
    VoicingOverrideResponse,
)
from app.solo_inference import infer_solo
import app.ingest as ingest

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
    stems = separate_with_demucs(
        prepared.normalized_wav_path,
        prepared.job_dir,
        chunk_paths=prepared.chunk_paths,
    )
    beat_grid_payload = estimate_beat_grid(
        prepared.normalized_wav_path,
        time_signature=time_signature_override,
        bpm_override=bpm_override,
    )
    backend_root = _backend_root().resolve()
    stem_abs_paths: dict[str, Path] = {}
    for key, rel in stems.items():
        stem_abs_paths[key] = backend_root / rel
    stem_routing = build_stem_routing_hints(stem_abs_paths)
    invalidated: list[str] = []
    if time_signature_override is not None or bpm_override is not None:
        invalidated = dependent_artifacts_for_grid_override()
    audio_chunk_paths = [str(p.relative_to(backend_root).as_posix()) for p in prepared.chunk_paths]
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
        logger.info("GET /analyze/%s — job not found, returning 404", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    logger.info("GET /analyze/%s status=%s", job_id, job.status)
    return job


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
    if not stems_dir.exists():
        raise HTTPException(status_code=400, detail="Stems missing. Run prepare first.")

    # Commit 111: Load persisted routing hints (sidecar) so chord/solo inference
    # uses the same stem selection as the main analysis pipeline. Fall back to
    # defaults if the sidecar is missing or unreadable.
    routing_path = job_dir / "stem_routing.json"
    routing_hints: StemRoutingHints
    if routing_path.exists():
        try:
            routing_hints = StemRoutingHints.model_validate_json(
                routing_path.read_text(encoding="utf-8")
            )
        except Exception:
            logger.exception("stem_routing read failed for job_id=%s; using defaults", job_id)
            routing_hints = StemRoutingHints()
    else:
        routing_hints = StemRoutingHints()

    stem_abs_paths = {
        k: stems_dir / f"{k}.wav"
        for k in ("guitar", "bass", "drums", "vocals", "piano", "other")
    }

    # Apply chord routing: try mix of bass+other, fall back to "other.wav" or full mix.
    chord_mix_path = stems_dir / "other.wav"  # legacy fallback
    try:
        valid_chord_stems = resolve_chord_stems(
            stem_abs_paths, routing_hints.chord_mix_stems
        )
        if len(valid_chord_stems) >= 2:
            chord_mix_path = mix_stems(valid_chord_stems, job_dir / "chord_mix.wav")
        elif not chord_mix_path.exists():
            # No bass+other available and no legacy "other.wav" — try full mix fallback
            song_wav = job_dir / "song.wav"
            if song_wav.exists():
                chord_mix_path = song_wav
        chord_timeline = infer_chords(chord_mix_path, beat_grid)
    except Exception:
        logger.exception("chord inference failed for job_id=%s", job_id)
        fallback = stems_dir / "other.wav"
        if fallback.exists():
            chord_mix_path = fallback
        chord_timeline = infer_chords(chord_mix_path, beat_grid)

    # Apply solo routing: cascade through selected → guitar → vocals.
    try:
        resolved_solo, _ = resolve_solo_stem(
            stem_abs_paths, routing_hints.selected_melodic_stem
        )
        solo_notes = infer_solo(resolved_solo, beat_grid)
    except Exception:
        logger.exception("solo inference failed for job_id=%s", job_id)
        guitar_path = stem_abs_paths.get("guitar")
        if guitar_path is not None and guitar_path.exists():
            solo_notes = infer_solo(guitar_path, beat_grid)
        else:
            raise HTTPException(status_code=400, detail="Required stems missing.")

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
        lesson_data["transcription_metadata"]["user_confirmed_at"] = __import__("datetime").datetime.now().isoformat()
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


# ---- Commit 109: Beat grid recompute endpoints ----------------------------

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
        raise HTTPException(status_code=404, detail=f"No recompute job for {job_id}.")
    return status


# ---- Commit 110: Correction endpoints ------------------------------------

import re as _re
import time as _time

_CHORD_SYMBOL_RE = _re.compile(r"^[A-G][#b]?(?:maj|min|dim|aug|sus[24]?|[2-9]|1[0-3]|7(?:#9|#5|b9|b5)?|alt)?$")
_CAGED_SHAPES = {"E-shape", "A-shape", "D-shape", "C-shape", "G-shape"}


def _get_lesson(job_id: str):
    """Return the JobStatus and its LessonJSON result, or raise 404."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if job.result is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} has no result yet.")
    return job


def _rebuild_musicxml(job_id: str) -> str:
    """Rebuild MusicXML from current chord_timeline + solo_notes + beat_grid_structured."""
    job = jobs.get(job_id)
    if job is None or job.result is None:
        return ""
    lesson = job.result
    beat_grid = lesson.beat_grid_structured
    chord_timeline = lesson.chord_timeline
    solo_notes = lesson.solo_notes
    if not beat_grid or not chord_timeline:
        return ""
    try:
        from app.musicxml_builder import build_musicxml
        return build_musicxml(
            beat_grid=beat_grid,
            chord_timeline=chord_timeline,
            solo_notes=solo_notes,
            title=lesson.song_title or "Harmoniq Score",
            artist=lesson.artist or "Harmoniq AI",
            key_signature=lesson.key,
        )
    except Exception:
        logger.exception("MusicXML rebuild failed for job_id=%s", job_id)
        return ""


@router.patch(
    "/analyze/{job_id}/chord/{beat_index}",
    response_model=ChordCorrectionResponse,
    summary="PATCH /analyze/{job_id}/chord/{beat_index} — correct a chord symbol",
)
async def correct_chord(job_id: str, beat_index: int, req: ChordCorrectionRequest) -> ChordCorrectionResponse:
    """Correct a chord symbol in the chord timeline."""
    job = _get_lesson(job_id)
    lesson = job.result
    if not lesson.chord_timeline or not lesson.chord_timeline.events:
        raise HTTPException(status_code=400, detail="No chord timeline available.")
    if beat_index < 0 or beat_index >= len(lesson.chord_timeline.events):
        raise HTTPException(status_code=400, detail=f"beat_index {beat_index} out of range (0-{len(lesson.chord_timeline.events) - 1}).")

    event = lesson.chord_timeline.events[beat_index]
    original_chord = event.chord
    corrected_chord = req.chord.strip()

    if not corrected_chord:
        raise HTTPException(status_code=400, detail="Chord symbol cannot be empty.")

    # Store original for history (using extra fields allowed by model_config)
    if not hasattr(event, "_original_chord") or not getattr(event, "_original_chord", None):
        event._original_chord = original_chord  # type: ignore[attr-defined]

    # Update chord
    new_events = list(lesson.chord_timeline.events)
    new_events[beat_index] = event.model_copy(update={"chord": corrected_chord, "confidence": 1.0})
    new_timeline = lesson.chord_timeline.model_copy(update={"events": new_events})

    # Update lesson in memory
    patched = lesson.model_copy(update={"chord_timeline": new_timeline})
    jobs[job_id] = job.model_copy(update={"result": patched})

    # Rebuild MusicXML
    musicxml_str = _rebuild_musicxml(job_id)
    if musicxml_str:
        final = jobs[job_id].result.model_copy(update={"musicxml": musicxml_str})
        jobs[job_id] = jobs[job_id].model_copy(update={"result": final})

    save_job_to_disk(job_id)

    return ChordCorrectionResponse(
        event_index=beat_index,
        original_chord=original_chord,
        corrected_chord=corrected_chord,
        chord_timeline=new_timeline,
    )


@router.patch(
    "/analyze/{job_id}/solo-note/{note_index}",
    response_model=NoteCorrectionResponse,
    summary="PATCH /analyze/{job_id}/solo-note/{note_index} — correct a solo note",
)
async def correct_solo_note(job_id: str, note_index: int, req: NoteCorrectionRequest) -> NoteCorrectionResponse:
    """Correct a solo note's pitch, duration, or start time."""
    job = _get_lesson(job_id)
    lesson = job.result
    if not lesson.solo_notes or not lesson.solo_notes.notes:
        raise HTTPException(status_code=400, detail="No solo notes available.")
    if note_index < 0 or note_index >= len(lesson.solo_notes.notes):
        raise HTTPException(status_code=400, detail=f"note_index {note_index} out of range (0-{len(lesson.solo_notes.notes) - 1}).")

    note = lesson.solo_notes.notes[note_index]
    original_pitch = note.pitch
    original_duration = note.duration

    update_fields: dict = {}
    if req.pitch is not None:
        update_fields["pitch"] = req.pitch
    if req.duration is not None:
        update_fields["duration"] = req.duration
    if req.start_time is not None:
        update_fields["start_time"] = req.start_time
    if req.velocity is not None:
        update_fields["velocity"] = req.velocity

    if not update_fields:
        raise HTTPException(status_code=400, detail="At least one field must be provided.")

    new_notes = list(lesson.solo_notes.notes)
    new_notes[note_index] = note.model_copy(update=update_fields)
    new_solo = lesson.solo_notes.model_copy(update={"notes": new_notes})

    patched = lesson.model_copy(update={"solo_notes": new_solo})
    jobs[job_id] = job.model_copy(update={"result": patched})

    musicxml_str = _rebuild_musicxml(job_id)
    if musicxml_str:
        final = jobs[job_id].result.model_copy(update={"musicxml": musicxml_str})
        jobs[job_id] = jobs[job_id].model_copy(update={"result": final})

    save_job_to_disk(job_id)

    return NoteCorrectionResponse(
        note_index=note_index,
        original_pitch=original_pitch,
        corrected_pitch=update_fields.get("pitch", original_pitch),
        original_duration=original_duration,
        corrected_duration=update_fields.get("duration", original_duration),
        solo_notes=new_solo,
    )


@router.patch(
    "/analyze/{job_id}/chord/{beat_index}/voicing",
    response_model=VoicingOverrideResponse,
    summary="PATCH /analyze/{job_id}/chord/{beat_index}/voicing — set voicing shape",
)
async def set_voicing_override(job_id: str, beat_index: int, req: VoicingOverrideRequest) -> VoicingOverrideResponse:
    """Set a CAGED voicing shape override for a chord."""
    job = _get_lesson(job_id)
    lesson = job.result
    if not lesson.chord_timeline or not lesson.chord_timeline.events:
        raise HTTPException(status_code=400, detail="No chord timeline available.")
    if beat_index < 0 or beat_index >= len(lesson.chord_timeline.events):
        raise HTTPException(status_code=400, detail=f"beat_index {beat_index} out of range.")

    shape = req.voicing_shape.strip()
    if shape not in _CAGED_SHAPES:
        raise HTTPException(status_code=400, detail=f"Invalid voicing shape. Must be one of: {', '.join(sorted(_CAGED_SHAPES))}")

    event = lesson.chord_timeline.events[beat_index]
    if not hasattr(event, "_voicing_override") or not getattr(event, "_voicing_override", None):
        event._voicing_override = shape  # type: ignore[attr-defined]

    new_events = list(lesson.chord_timeline.events)
    new_events[beat_index] = event.model_copy(update={"_voicing_override": shape})
    new_timeline = lesson.chord_timeline.model_copy(update={"events": new_events})

    patched = lesson.model_copy(update={"chord_timeline": new_timeline})
    jobs[job_id] = job.model_copy(update={"result": patched})
    save_job_to_disk(job_id)

    return VoicingOverrideResponse(
        event_index=beat_index,
        voicing_shape=shape,
        chord_timeline=new_timeline,
    )


@router.get(
    "/analyze/{job_id}/corrections",
    response_model=CorrectionHistoryResponse,
    summary="GET /analyze/{job_id}/corrections — correction history",
)
async def get_corrections(job_id: str) -> CorrectionHistoryResponse:
    """Return all corrections applied to a job."""
    job = _get_lesson(job_id)
    lesson = job.result
    corrections: list[CorrectionHistoryItem] = []

    # Scan chord timeline for corrections
    if lesson.chord_timeline and lesson.chord_timeline.events:
        for i, ev in enumerate(lesson.chord_timeline.events):
            orig = getattr(ev, "_original_chord", None)
            if orig and orig != ev.chord:
                corrections.append(CorrectionHistoryItem(
                    id=f"chord_{i}",
                    type="chord",
                    event_or_note_index=i,
                    original_value=orig,
                    corrected_value=ev.chord,
                    timestamp=float(getattr(ev, "_correction_timestamp", _time.time())),
                ))
            voicing = getattr(ev, "_voicing_override", None)
            if voicing:
                corrections.append(CorrectionHistoryItem(
                    id=f"voicing_{i}",
                    type="voicing",
                    event_or_note_index=i,
                    original_value=None,
                    corrected_value=voicing,
                    timestamp=float(getattr(ev, "_correction_timestamp", _time.time())),
                ))

    total_events = (
        (len(lesson.chord_timeline.events) if lesson.chord_timeline else 0)
        + (len(lesson.solo_notes.notes) if lesson.solo_notes else 0)
    )
    chord_note_corrections = sum(1 for c in corrections if c.type in ("chord", "note"))
    coverage = chord_note_corrections / total_events if total_events > 0 else 0.0

    return CorrectionHistoryResponse(
        corrections=corrections,
        correction_count=chord_note_corrections,
        correction_coverage=round(coverage, 4),
    )


@router.get(
    "/analyze/{job_id}/corrections/export",
    response_model=CorrectionExportResponse,
    summary="GET /analyze/{job_id}/corrections/export — export corrections as training data",
)
async def export_corrections(job_id: str) -> CorrectionExportResponse:
    """Export corrections as JSON suitable for ML retraining."""
    job = _get_lesson(job_id)
    lesson = job.result

    chord_corrections: list[dict] = []
    if lesson.chord_timeline and lesson.chord_timeline.events:
        for i, ev in enumerate(lesson.chord_timeline.events):
            orig = getattr(ev, "_original_chord", None)
            if orig and orig != ev.chord:
                chord_corrections.append({
                    "event_index": i,
                    "timestamp": ev.timestamp,
                    "original": orig,
                    "corrected": ev.chord,
                    "confidence": ev.confidence,
                })

    note_corrections: list[dict] = []
    if lesson.solo_notes and lesson.solo_notes.notes:
        for i, note in enumerate(lesson.solo_notes.notes):
            # Note corrections are tracked via the frontend correction store,
            # not stored on the backend model. Export what we have.
            pass

    return CorrectionExportResponse(
        job_id=job_id,
        song_title=lesson.song_title,
        artist=lesson.artist,
        key=lesson.key,
        chord_corrections=chord_corrections,
        note_corrections=note_corrections,
    )
