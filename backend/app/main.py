"""Harmoniq API entrypoint — health, CORS, async analyze job polling (PRIORITIES §4)."""

from __future__ import annotations

import json
import logging
import inspect
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import (
    AnalyzeJobCreated,
    JamScoreRequest,
    JamScoreResult,
    JobStatus,
    OnboardingPlacementRequest,
    OnboardingPlacementResponse,
    PlayerProfile,
    QuickFeedbackRequest,
    QuickFeedbackResponse,
    ScoreRequest,
    ScoreResult,
)
from app.ingest import get_job_dir
from app.jobs import ANALYSIS_FAILED_USER_MESSAGE, enqueue_analyze_job, jobs
from app.coach import (
    generate_jam_coach_summary,
    generate_onboarding_placement_summary,
    generate_quick_feedback,
)
from app.score import score_recording

logger = logging.getLogger("harmoniq.api")
logger.setLevel(logging.INFO)


def _parse_player_profile_field(raw: object) -> PlayerProfile | None:
    """Accept JSON object or JSON string; invalid payloads are dropped (safe generic coaching)."""
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
    try:
        return PlayerProfile.model_validate(data)
    except Exception:
        logger.warning("player_profile validation failed; ignoring")
        return None

app = FastAPI(
    title="Harmoniq API",
    description="Local analysis backend for Harmoniq (in-memory job runner; real pipeline later).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
    ],
    # Expo / Metro may use any port (e.g. `expo start --port 8082`); without this, OPTIONS preflight
    # returns 400 and the browser shows a network-style failure ("need a connection…").
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


@app.get(
    "/lesson-file",
    tags=["Artifacts"],
    summary="Serve a lesson stem or other job-relative audio file (PRIORITIES §20)",
)
async def lesson_file(
    rel: str = Query(..., description="Path relative to backend root, e.g. data/jobs/…/stems/guitar.wav"),
) -> FileResponse:
    """Return WAV/audio from disk; used by the app to decode stems referenced in LessonJSON.stems."""
    backend_root = _backend_root().resolve()
    rel_norm = rel.replace("\\", "/").lstrip("/")
    if not rel_norm or ".." in Path(rel_norm).parts:
        raise HTTPException(status_code=400, detail="Invalid rel path")
    candidate = (backend_root / rel_norm).resolve()
    if not str(candidate).startswith(str(backend_root)):
        raise HTTPException(status_code=403, detail="Path escapes backend root")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    suffix = candidate.suffix.lower()
    media = "audio/wav" if suffix == ".wav" else "application/octet-stream"
    return FileResponse(candidate, media_type=media, filename=candidate.name)


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # per README: max 50MB


class UploadTooLargeError(ValueError):
    pass


async def _save_uploadfile_limited(
    upload: UploadFile,
    dest_path: Path,
    *,
    max_bytes: int,
    chunk_bytes: int = 1024 * 1024,
) -> None:
    """Stream UploadFile to disk while enforcing a hard byte limit."""
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


@app.post(
    "/analyze",
    response_model=AnalyzeJobCreated,
    tags=["Analyze"],
    summary="POST /analyze (async — returns job_id immediately)",
)


async def analyze(request: Request) -> AnalyzeJobCreated:
    """POST /analyze: JSON youtube_url or multipart upload."""
    job_id = str(uuid.uuid4())

    youtube_url: str | None = None
    upload_path: str | None = None
    player_profile: PlayerProfile | None = None

    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            youtube_url = form.get("youtube_url") or form.get("url")  # accept both keys
            player_profile = _parse_player_profile_field(form.get("player_profile"))

            if upload is not None:
                suffix = Path(upload.filename or "").suffix or ".audio"
                job_dir = get_job_dir(job_id)
                dest = job_dir / f"input{suffix}"
                if isinstance(upload, UploadFile):
                    await _save_uploadfile_limited(
                        upload,
                        dest,
                        max_bytes=MAX_UPLOAD_BYTES,
                    )
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

        else:
            body = await request.json()
            if isinstance(body, dict):
                youtube_url = body.get("url") or body.get("youtube_url")
                player_profile = _parse_player_profile_field(body.get("player_profile"))

    except UploadTooLargeError:
        logger.warning("POST /analyze upload too large job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE)
        return AnalyzeJobCreated(job_id=job_id)

    except Exception:
        logger.exception("POST /analyze failed to parse input job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE)
        return AnalyzeJobCreated(job_id=job_id)

    logger.info(
        "POST /analyze created job_id=%s status=processing youtube_url=%r upload_path=%r",
        job_id,
        youtube_url,
        upload_path,
    )

    enqueue_analyze_job(
        job_id=job_id,
        youtube_url=youtube_url,
        upload_path=upload_path,
        player_profile=player_profile,
    )
    return AnalyzeJobCreated(job_id=job_id)


@app.get(
    "/analyze/{job_id}",
    response_model=JobStatus,
    tags=["Analyze"],
    summary="GET /analyze/{job_id}",
)
async def analyze_status(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.warning("GET /analyze/%s — unknown job_id (404)", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    logger.info("GET /analyze/%s status=%s", job_id, job.status)
    return job


@app.post(
    "/score",
    response_model=ScoreResult,
    tags=["Score"],
    summary="POST /score",
)
async def score(payload: ScoreRequest) -> ScoreResult:
    try:
        return score_recording(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/onboarding-placement",
    response_model=OnboardingPlacementResponse,
    tags=["Onboarding"],
    summary="POST /onboarding-placement — placement baseline coach paragraph",
)
async def onboarding_placement(payload: OnboardingPlacementRequest) -> OnboardingPlacementResponse:
    paragraph = generate_onboarding_placement_summary(
        pitch_avg=payload.pitch_avg,
        phrasing_avg=payload.phrasing_avg,
        timing_avg=payload.timing_avg,
        bend_error_cents_avg=payload.bend_error_cents_avg,
    )
    return OnboardingPlacementResponse(coach_paragraph=paragraph)


@app.post(
    "/quick-feedback",
    response_model=QuickFeedbackResponse,
    tags=["Coach"],
    summary="POST /quick-feedback — Play step per-beat accuracy coach line",
)
async def quick_feedback(payload: QuickFeedbackRequest) -> QuickFeedbackResponse:
    message = generate_quick_feedback([str(x) for x in payload.accuracy_pattern])
    return QuickFeedbackResponse(message=message)


@app.post(
    "/jam-score",
    response_model=JamScoreResult,
    tags=["Jam"],
    summary="POST /jam-score — jam session summary (stub → incremental)",
)
async def jam_score(payload: JamScoreRequest) -> JamScoreResult:
    client_map = {k: float(v) for k, v in (payload.scale_position_map or {}).items()}
    coach = generate_jam_coach_summary(
        duration_seconds=int(payload.duration_seconds),
        inferred_scale_label=payload.inferred_scale_label,
        scale_position_map=client_map,
    )
    merged = dict(client_map)
    if int(payload.duration_seconds) >= 10 and client_map:
        top = max(client_map.items(), key=lambda kv: kv[1])
        merged["focus_pitch_class"] = float(top[1])
    return JamScoreResult(coach_summary=coach, scale_position_map=merged)
