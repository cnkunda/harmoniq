"""Redis-backed job store — replaces the in-memory `jobs` dict from Phase 1.

Provides the same interface as the old in-memory dict, but persists job state
in Redis so multiple workers can read/write concurrently.

Redis key schema:
  job:{job_id}          — hash with fields: status, result_json, error, error_code,
                          progress, stage_label, processing_started_at, analysis_stage
  coach:{job_id}        — hash with coach hydration state
  dlq:{job_id}          — dead-letter queue entry (failed jobs)
  sse:channel:{job_id}  — pub/sub channel for SSE events
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from app.schemas import (
    CoachHydrationSection,
    CoachHydrationStatus,
    JobStatus,
)

logger = logging.getLogger("harmoniq.job_store")

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

_redis_client = None


def _get_redis():
    """Lazy Redis connection singleton."""
    global _redis_client
    if _redis_client is None:
        import redis as redis_mod

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis_mod.Redis.from_url(url, decode_responses=True)
    return _redis_client


def get_redis():
    """Public accessor for the Redis client (used by metrics, SSE, DLQ)."""
    return _get_redis()


def ping() -> bool:
    """Health-check: returns True if Redis responds to PING."""
    try:
        return get_redis().ping()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Job state helpers
# ---------------------------------------------------------------------------

_JOB_PREFIX = "job:"
_COACH_PREFIX = "coach:"
_JOB_TTL_SECONDS = int(os.getenv("HARMONIQ_JOB_TTL_HOURS", "24")) * 3600


def _job_key(job_id: str) -> str:
    return f"{_JOB_PREFIX}{job_id}"


def _coach_key(job_id: str) -> str:
    return f"{_COACH_PREFIX}{job_id}"


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------


def create_job(job_id: str, status: JobStatus) -> None:
    """Insert a new job into Redis."""
    r = get_redis()
    data = status.model_dump(mode="json")
    r.hset(_job_key(job_id), mapping={k: json.dumps(v) if v is not None else "" for k, v in data.items()})
    r.expire(_job_key(job_id), _JOB_TTL_SECONDS)
    logger.debug("create_job job_id=%s status=%s", job_id, status.status)


def get_job(job_id: str) -> JobStatus | None:
    """Retrieve a job from Redis, or None if missing/expired."""
    r = get_redis()
    raw = r.hgetall(_job_key(job_id))
    if not raw:
        return None
    return _parse_job_status(raw)


def update_job(job_id: str, **fields: Any) -> None:
    """Patch one or more fields on an existing job hash."""
    r = get_redis()
    mapping: dict[str, str] = {}
    for k, v in fields.items():
        mapping[k] = json.dumps(v) if v is not None else ""
    if mapping:
        r.hset(_job_key(job_id), mapping=mapping)
        r.expire(_job_key(job_id), _JOB_TTL_SECONDS)


def set_job_status(job_id: str, status: JobStatus) -> None:
    """Overwrite the full job hash (used when transitioning to complete/failed)."""
    r = get_redis()
    data = status.model_dump(mode="json")
    r.hset(_job_key(job_id), mapping={k: json.dumps(v) if v is not None else "" for k, v in data.items()})
    r.expire(_job_key(job_id), _JOB_TTL_SECONDS)


def delete_job(job_id: str) -> None:
    """Remove a job from Redis."""
    r = get_redis()
    r.delete(_job_key(job_id))


def set_job_progress(job_id: str, progress: float, stage_label: str, analysis_stage: str | None = None) -> None:
    """Update progress and stage label for an in-flight job."""
    fields: dict[str, Any] = {
        "progress": max(0.0, min(1.0, float(progress))),
        "stage_label": stage_label,
    }
    if analysis_stage is not None:
        fields["analysis_stage"] = analysis_stage
    update_job(job_id, **fields)


def set_job_processing(job_id: str, processing_started_at: float | None = None) -> None:
    """Mark a job as processing."""
    update_job(
        job_id,
        status="processing",
        result=None,
        error=None,
        error_code=None,
        progress=0.05,
        stage_label="Queued…",
        processing_started_at=processing_started_at or time.time(),
    )


def set_job_complete(job_id: str, result: Any) -> None:
    """Mark a job as complete with the lesson result."""
    set_job_status(
        job_id,
        JobStatus(status="complete", result=result, error=None),
    )


def set_job_failed(job_id: str, error: str, error_code: str | None = None) -> None:
    """Mark a job as failed with an error message."""
    set_job_status(
        job_id,
        JobStatus(status="failed", result=None, error=error, error_code=error_code),
    )


# ---------------------------------------------------------------------------
# Coach hydration store
# ---------------------------------------------------------------------------


def set_coach_hydration(job_id: str, status: CoachHydrationStatus) -> None:
    """Persist coach hydration status in Redis."""
    r = get_redis()
    data = status.model_dump(mode="json")
    r.hset(_coach_key(job_id), mapping={k: json.dumps(v) if v is not None else "" for k, v in data.items()})
    r.expire(_coach_key(job_id), _JOB_TTL_SECONDS)


def get_coach_hydration(job_id: str) -> CoachHydrationStatus | None:
    """Retrieve coach hydration status from Redis."""
    r = get_redis()
    raw = r.hgetall(_coach_key(job_id))
    if not raw:
        return None
    return _parse_coach_status(raw)


def set_coach_pending(job_id: str, section_count: int) -> None:
    """Initialize coach hydration as pending."""
    set_coach_hydration(
        job_id,
        CoachHydrationStatus(
            status="pending",
            sections=[CoachHydrationSection(index=i, coach_note="", coach_explanation="") for i in range(max(0, section_count))],
            fallback_reason=None,
        ),
    )


# ---------------------------------------------------------------------------
# Dead-letter queue
# ---------------------------------------------------------------------------


def push_to_dlq(job_id: str, error: str, error_code: str | None = None, retry_count: int = 0) -> None:
    """Push a failed job to the dead-letter queue."""
    r = get_redis()
    entry = json.dumps({
        "job_id": job_id,
        "error": error,
        "error_code": error_code,
        "retry_count": retry_count,
        "timestamp": time.time(),
    })
    r.lpush("dlq:jobs", entry)
    r.expire(f"dlq:{job_id}", _JOB_TTL_SECONDS)
    logger.warning("push_to_dlq job_id=%s error=%s", job_id, error)


def pop_from_dlq() -> dict | None:
    """Pop the most recent entry from the dead-letter queue."""
    r = get_redis()
    raw = r.rpop("dlq:jobs")
    if raw is None:
        return None
    return json.loads(raw)


def dlq_length() -> int:
    """Return the number of jobs in the dead-letter queue."""
    return get_redis().llen("dlq:jobs")


def inspect_dlq(limit: int = 50) -> list[dict]:
    """Inspect the dead-letter queue without consuming entries."""
    r = get_redis()
    raw = r.lrange("dlq:jobs", 0, limit - 1)
    return [json.loads(entry) for entry in raw]


# ---------------------------------------------------------------------------
# SSE pub/sub
# ---------------------------------------------------------------------------


def publish_sse_event(job_id: str, event: str, data: dict) -> None:
    """Publish an SSE event to a job's channel."""
    r = get_redis()
    channel = f"sse:channel:{job_id}"
    payload = json.dumps({"event": event, "data": data})
    r.publish(channel, payload)


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------


def _parse_job_status(raw: dict[str, str]) -> JobStatus:
    """Parse a Redis hash back into a JobStatus model."""
    def _get(key: str, default: Any = None) -> Any:
        val = raw.get(key, "")
        if val == "" or val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    result_data = _get("result")
    from app.schemas import LessonJSON

    result = LessonJSON.model_validate(result_data) if result_data else None

    return JobStatus(
        status=_get("status", "processing"),
        result=result,
        error=_get("error"),
        error_code=_get("error_code"),
        progress=_get("progress"),
        stage_label=_get("stage_label"),
        processing_started_at=_get("processing_started_at"),
    )


def _parse_coach_status(raw: dict[str, str]) -> CoachHydrationStatus:
    """Parse a Redis hash back into a CoachHydrationStatus model."""
    def _get(key: str, default: Any = None) -> Any:
        val = raw.get(key, "")
        if val == "" or val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    sections_raw = _get("sections", [])
    sections = [CoachHydrationSection(**s) for s in sections_raw] if sections_raw else []

    return CoachHydrationStatus(
        status=_get("status", "pending"),
        sections=sections,
        fallback_reason=_get("fallback_reason"),
    )
