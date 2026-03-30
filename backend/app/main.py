"""Harmoniq API entrypoint — health, CORS, async analyze job polling (PRIORITIES §4)."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AnalyzeJobCreated,
    AnalyzeRequest,
    JobStatus,
)
from app.jobs import enqueue_analyze_job, jobs

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


@app.post(
    "/analyze",
    response_model=AnalyzeJobCreated,
    tags=["Analyze"],
    summary="POST /analyze (async — returns job_id immediately)",
)
async def analyze(body: AnalyzeRequest) -> AnalyzeJobCreated:
    """JSON `{ url }` only; multipart upload lands in PRIORITIES §5."""
    job_id = str(uuid.uuid4())
    logger.info(
        "POST /analyze created job_id=%s status=processing url=%r",
        job_id,
        body.url,
    )
    # Enqueue immediately; worker runs after response is sent.
    enqueue_analyze_job(job_id=job_id, url=body.url)
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
