"""Harmoniq API entrypoint — health + OpenAPI stubs (commit 0.2)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.schemas import AnalyzeRequest, JobStatus

app = FastAPI(
    title="Harmoniq API",
    description="Local analysis backend for Harmoniq (scaffold — pipeline in later commits).",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/analyze",
    status_code=501,
    tags=["Stubs"],
    summary="POST /analyze (not implemented)",
    response_description="Not implemented in 0.2",
    response_model=JobStatus,
)
async def analyze_stub(_body: AnalyzeRequest) -> JobStatus:
    """Accepts JSON shape for YouTube URL; multipart audio comes in a later commit."""
    raise HTTPException(
        status_code=501,
        detail="Analysis pipeline not implemented yet (commit 0.2 scaffold only).",
    )


@app.get(
    "/analyze/{job_id}",
    status_code=501,
    tags=["Stubs"],
    summary="GET /analyze/{job_id} (not implemented)",
    response_model=JobStatus,
)
async def analyze_status_stub(job_id: str) -> JobStatus:
    _ = job_id
    raise HTTPException(
        status_code=501,
        detail="Job polling not implemented yet (commit 0.2 scaffold only).",
    )
