"""WebSocket endpoint for real-time job progress push.

Subscribes to Redis pub/sub channel `job:{job_id}:progress` and forwards
messages to the client. Falls back to polling if Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("harmoniq.api.ws")

router = APIRouter(tags=["WebSocket"])

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def _redis_listener(
    websocket: WebSocket,
    job_id: str,
    pubsub,
) -> None:
    """Listen on Redis pub/sub and forward messages to the WebSocket."""
    try:
        await pubsub.subscribe(f"job:{job_id}:progress")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            try:
                await websocket.send_text(data)
                payload = json.loads(data)
                if payload.get("type") in ("complete", "failed"):
                    break
            except Exception:
                break
    finally:
        try:
            await pubsub.unsubscribe(f"job:{job_id}:progress")
        except Exception:
            logger.debug("pubsub unsubscribe failed job_id=%s", job_id, exc_info=True)


async def _poll_fallback(
    websocket: WebSocket,
    job_id: str,
) -> None:
    """Fallback HTTP polling if Redis is unavailable.

    Periodically checks `GET /analyze/{job_id}` and forwards status
    to the WebSocket client. This ensures WS clients still get updates
    even when Redis is down.
    """
    try:
        import httpx
    except ImportError:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Polling fallback unavailable (httpx not installed)"})
        )
        return

    api_base = os.getenv("HARMONIQ_API_BASE", f"http://localhost:{os.getenv('PORT', '8000')}")
    url = f"{api_base}/analyze/{job_id}"

    terminal = {"complete", "failed"}
    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    msg = json.dumps({"type": "status", **data})
                    await websocket.send_text(msg)
                    if data.get("status") in terminal:
                        if data["status"] == "complete":
                            await websocket.send_text(
                                json.dumps({"type": "complete", "result": data.get("result")})
                            )
                        else:
                            await websocket.send_text(
                                json.dumps({
                                    "type": "failed",
                                    "error": data.get("error", "Analysis failed"),
                                    "error_code": data.get("error_code"),
                                })
                            )
                        break
        except Exception:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Status check failed"})
            )
        await asyncio.sleep(2)


@router.websocket("/ws/analyze/{job_id}")
async def ws_analyze_status(websocket: WebSocket, job_id: str):
    """WebSocket: receive real-time job progress updates.

    Usage:
        ws://host:8000/ws/analyze/{job_id}

    Messages are JSON-encoded:
        {"type":"status","status":"processing","progress":0.62,"stage_label":"Transcribing (MT3)…"}
        {"type":"complete","result":{...LessonJSON...}}
        {"type":"failed","error":"...","error_code":"..."}
    """
    await websocket.accept()
    logger.info("WS connected job_id=%s", job_id)

    # Send initial status immediately
    try:
        from app.repository import get_job as _repo_get
        job = _repo_get(job_id)
        if job is not None:
            await websocket.send_text(
                json.dumps({
                    "type": "status",
                    "status": job.status,
                    "progress": job.progress,
                    "stage_label": job.stage_label,
                    "analysis_stage": job.analysis_stage,
                })
            )
            if job.status == "complete" and job.result is not None:
                await websocket.send_text(
                    json.dumps({"type": "complete", "result": job.result.model_dump(exclude_none=True)})
                )
                await websocket.close()
                return
            if job.status == "failed":
                await websocket.send_text(
                    json.dumps({"type": "failed", "error": job.error, "error_code": job.error_code})
                )
                await websocket.close()
                return
    except Exception:
        logger.warning("WS initial status send failed job_id=%s", job_id, exc_info=True)

    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(REDIS_URL)
        pubsub = r.pubsub()
        # Check if Redis is actually available with a quick ping
        await r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
        logger.info("Redis not available for WS job_id=%s; using polling fallback", job_id)

    try:
        if redis_ok:
            await _redis_listener(websocket, job_id, pubsub)
        else:
            await _poll_fallback(websocket, job_id)
    except WebSocketDisconnect:
        logger.info("WS disconnected job_id=%s", job_id)
    except Exception:
        logger.exception("WS error job_id=%s", job_id)
    finally:
        try:
            await websocket.close()
        except Exception:
            logger.debug("websocket close failed job_id=%s", job_id, exc_info=True)
        if redis_ok:
            try:
                await pubsub.unsubscribe(f"job:{job_id}:progress")
                await r.close()
            except Exception:
                logger.debug("pubsub cleanup failed job_id=%s", job_id, exc_info=True)
