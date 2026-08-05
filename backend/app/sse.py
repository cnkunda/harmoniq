"""Server-Sent Events (SSE) utilities for Harmoniq.

Provides an EventSourceResponse wrapper and helper to stream
job progress updates to connected clients.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator

from starlette.responses import StreamingResponse

logger = logging.getLogger("harmoniq.sse")


def format_sse_event(event: str, data: dict | str) -> str:
    """Format a single SSE message in the `event: ...\ndata: ...\n\n` format."""
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def job_progress_stream(job_id: str) -> AsyncIterator[str]:
    """Yield SSE events for a job by polling Redis pub/sub.

    Subscribes to `sse:channel:{job_id}` and yields events until
    the job reaches a terminal state (complete/failed).
    """
    import redis.asyncio as aioredis

    from app.job_store import get_job

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    r = aioredis.from_url(url, decode_responses=True)
    pubsub = r.pubsub()
    channel = f"sse:channel:{job_id}"
    await pubsub.subscribe(channel)

    try:
        # Send initial heartbeat
        yield format_sse_event("connected", {"job_id": job_id, "message": "SSE connected"})

        # Check if job is already complete
        job = get_job(job_id)
        if job is not None:
            if job.status == "complete":
                yield format_sse_event("complete", job.model_dump(mode="json"))
                return
            elif job.status == "failed":
                yield format_sse_event("error", {"error": job.error, "error_code": job.error_code})
                return

        connection_start = time.time()
        last_heartbeat = connection_start
        timeout_seconds = 900  # 15 minutes max SSE connection

        while True:
            now = time.time()

            # Timeout safety — compare against connection start, not last heartbeat
            if now - connection_start > timeout_seconds:
                yield format_sse_event("error", {"error": "SSE connection timed out"})
                return

            message = await pubsub.get_message(timeout=1.0)
            if message is not None and message["type"] == "message":
                payload = json.loads(message["data"])
                event_type = payload.get("event", "progress")
                event_data = payload.get("data", {})

                yield format_sse_event(event_type, event_data)

                # Terminal events close the stream
                if event_type in ("complete", "error"):
                    return

            # Heartbeat every 15s to keep connection alive
            now = time.time()
            if now - last_heartbeat > 15:
                yield format_sse_event("heartbeat", {"ts": now})
                last_heartbeat = now

    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()


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
