"""In-memory job registry for async jam-backing generation (J2).

Personal-scale: bounded, TTL-pruned, no external broker. Audio bytes stay in
process only until the client collects them (or the TTL expires).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

from app.music_generation.types import GeneratedBacking

JOB_TTL_SECONDS = 3600
MAX_JOBS = 32

_JOBS: dict[str, "BackingJob"] = {}
_LOCK = threading.Lock()

BackingJobStatus = Literal["queued", "processing", "complete", "failed"]


@dataclass
class BackingJob:
    job_id: str
    status: BackingJobStatus = "queued"
    result: GeneratedBacking | None = None
    error: str | None = None
    created_at: float = 0.0


def _prune_locked(now: float) -> None:
    expired = [jid for jid, job in _JOBS.items() if now - job.created_at > JOB_TTL_SECONDS]
    for jid in expired:
        _JOBS.pop(jid, None)
    if len(_JOBS) > MAX_JOBS:
        for jid, _ in sorted(_JOBS.items(), key=lambda item: item[1].created_at)[: len(_JOBS) - MAX_JOBS]:
            _JOBS.pop(jid, None)


def create_job(job_id: str) -> BackingJob:
    now = time.time()
    with _LOCK:
        _prune_locked(now)
        job = BackingJob(job_id=job_id, created_at=now)
        _JOBS[job_id] = job
        return job


def get_job(job_id: str) -> BackingJob | None:
    now = time.time()
    with _LOCK:
        _prune_locked(now)
        return _JOBS.get(job_id)


def mark_processing(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.status = "processing"


def complete_job(job_id: str, result: GeneratedBacking) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.status = "complete"
            job.result = result


def fail_job(job_id: str, error: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.status = "failed"
            job.error = error


def clear_jobs() -> None:
    """Test helper."""
    with _LOCK:
        _JOBS.clear()
