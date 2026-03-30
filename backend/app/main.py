"""Harmoniq API entrypoint — health, CORS, async analyze job polling (PRIORITIES §4)."""

from __future__ import annotations

import logging
import inspect
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AnalyzeJobCreated,
    JobStatus,
)
from app.ingest import get_job_dir
from app.jobs import ANALYSIS_FAILED_USER_MESSAGE, enqueue_analyze_job, jobs

logger = logging.getLogger("harmoniq.api")
logger.setLevel(logging.INFO)

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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

    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            youtube_url = form.get("youtube_url") or form.get("url")  # accept both keys

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
