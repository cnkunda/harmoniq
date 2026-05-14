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
    get_coach_hydration,
    jobs,
)
from app.schemas import (
    AnalyzeJobCreated,
    AnalyzeTranscriptionResponse,
    BeatGrid,
    CoachHydrationStatus,
    JobStatus,
    TranscriptionPrepareResponse,
    TranscriptionVerifyRequest,
    TranscriptionVerifyResponse,
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


def _parse_player_profile_field(raw: object) -> object:
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
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            youtube_url = form.get("youtube_url") or form.get("url")
            player_profile = _parse_player_profile_field(form.get("player_profile"))
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
    enqueue_analyze_job(job_id=job_id, youtube_url=youtube_url, upload_path=upload_path, player_profile=player_profile)
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
    chord_timeline = infer_chords(chord_mix_path, beat_grid)
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
