"""Harmoniq API entrypoint — health, CORS, in-memory analyze stub (PRIORITIES §3)."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AnalyzeJobCreated,
    AnalyzeRequest,
    JobStatus,
    LessonJSON,
    LessonSectionStub,
)

logger = logging.getLogger("harmoniq.api")
logger.setLevel(logging.INFO)

# In-memory job store (single process). Values match GET /analyze/{job_id} JSON shape.
jobs: dict[str, JobStatus] = {}


def _stub_lesson(job_id: str, source_url: str | None) -> LessonJSON:
    """Deterministic fake lesson for client contract tests; pipeline replaces this later."""
    _ = source_url  # reserved for future ingest logging
    return LessonJSON(
        job_id=job_id,
        song_title="Stub Song",
        artist="Stub Artist",
        key="G major",
        key_confidence=0.99,
        tempo=72.0,
        tempo_confidence=0.95,
        transcription_confidence=0.5,
        beat_grid=[0.0, 0.5, 1.0],
        bar_timestamps=[0.0, 3.33, 6.66],
        stems={},
        lyrics_aligned=[],
        sections=[
            LessonSectionStub(label="Solo (stub)", confidence=0.8),
        ],
    )


app = FastAPI(
    title="Harmoniq API",
    description="Local analysis backend for Harmoniq (in-memory analyze stub — real pipeline in later commits).",
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


@app.post(
    "/analyze",
    response_model=AnalyzeJobCreated,
    tags=["Analyze"],
    summary="POST /analyze (stub — returns job_id immediately)",
)
async def analyze(body: AnalyzeRequest) -> AnalyzeJobCreated:
    """JSON `{ url }` only; multipart upload lands in PRIORITIES §5."""
    job_id = str(uuid.uuid4())
    result = _stub_lesson(job_id, body.url)
    jobs[job_id] = JobStatus(status="complete", result=result, error=None)
    logger.info(
        "POST /analyze created job_id=%s status=complete (stub) url=%r",
        job_id,
        body.url,
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
