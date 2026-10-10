"""Server-Sent Events (SSE) utilities for Harmoniq.

Provides an SSE response wrapper and the job progress stream behind
`GET /analyze/{job_id}/stream`.

Commit 151 (BUG-01 root-cause fix): the stream watches the same in-memory
job store `GET /analyze/{job_id}` reads and emits an event on every state
change, instead of subscribing to Redis pub/sub. The previous
`sse:channel:{job_id}` subscription never received anything — no producer
ever published to that channel — and it required a running Redis even
though the analyze pipeline (thread worker and Celery alike) already keeps
job state readable in-process.

Event contract:
    connected  {"job_id", "message"}        first frame
    status     JobStatus JSON               on connect + on every change
    complete   JobStatus JSON (with result) terminal — stream closes
    failed     JobStatus JSON               terminal — stream closes
    heartbeat  {"ts"}                       every HEARTBEAT_SECONDS while idle
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from starlette.responses import StreamingResponse

from app.schemas import JobStatus

logger = logging.getLogger("harmoniq.sse")

# How often the job store is checked for changes (seconds).
POLL_INTERVAL_SECONDS = 1.0
# Keep-alive frames so proxies don't time out a silent stream.
HEARTBEAT_SECONDS = 15.0
# Hard cap on a single stream connection.
TIMEOUT_SECONDS = 900.0


def format_sse_event(event: str, data: dict | str) -> str:
    """Format a single SSE message in the `event: ...\ndata: ...\n\n` format."""
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


def _status_snapshot(job: JobStatus) -> tuple[Any, ...]:
    """Fields whose change should emit a `status` event (result arrives only at terminal)."""
    return (
        job.status,
        job.progress,
        job.stage_label,
        job.processing_started_at,
        job.analysis_stage,
        job.error,
        job.error_code,
        # Commit 152: partial chord payload — equality on the pydantic model
        # detects arrival so the preview renders as soon as chords are ready.
        job.partial_result,
    )


async def job_progress_stream(job_id: str) -> AsyncIterator[str]:
    """Yield SSE events for a job by watching the in-memory job store.

    Mirrors `GET /analyze/{job_id}` semantics (unknown id → queued), emits
    `status` only when the snapshot actually changes, and ends the stream on
    the first terminal status — no frames are produced after `complete`/`failed`.
    """
    from app.jobs import jobs  # heavy module — import lazily, like this router already does

    def current_job() -> JobStatus:
        job = jobs.get(job_id)
        if job is None:
            return JobStatus(status="queued", result=None, error=None, error_code=None)
        return job

    connection_start = time.monotonic()
    last_heartbeat = connection_start
    last_snapshot: tuple[Any, ...] | None = None

    try:
        yield format_sse_event("connected", {"job_id": job_id, "message": "SSE connected"})

        while True:
            job = current_job()

            if job.status in ("complete", "failed"):
                event = "complete" if job.status == "complete" else "failed"
                yield format_sse_event(event, job.model_dump(mode="json"))
                return

            snapshot = _status_snapshot(job)
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield format_sse_event("status", job.model_dump(mode="json"))

            now = time.monotonic()
            if now - connection_start > TIMEOUT_SECONDS:
                yield format_sse_event(
                    "failed",
                    JobStatus(
                        status="failed",
                        result=None,
                        error="SSE connection timed out",
                        error_code=None,
                    ).model_dump(mode="json"),
                )
                return
            if now - last_heartbeat > HEARTBEAT_SECONDS:
                last_heartbeat = now
                yield format_sse_event("heartbeat", {"ts": time.time()})

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        logger.debug("SSE stream closed job_id=%s", job_id)


def sse_response(job_id: str) -> StreamingResponse:
    """Create a StreamingResponse that streams SSE events for a job."""
    return StreamingResponse(
        job_progress_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
