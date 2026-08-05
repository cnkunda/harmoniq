"""Dead-letter queue (DLQ) for Harmoniq.

Failed jobs that exhaust retries are pushed here for inspection and reprocessing.
Uses Redis lists under the `dlq:jobs` key.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("harmoniq.dead_letter")


def push_to_dlq(
    job_id: str,
    error: str,
    error_code: str | None = None,
    retry_count: int = 0,
    job_data: dict | None = None,
) -> None:
    """Push a failed job to the dead-letter queue.

    Args:
        job_id: The failed job's identifier.
        error: User-safe error message.
        error_code: Machine-readable error code.
        retry_count: Number of retry attempts before failure.
        job_data: Optional original job parameters for reprocessing.
    """
    from app.job_store import get_redis

    r = get_redis()
    entry = json.dumps({
        "job_id": job_id,
        "error": error,
        "error_code": error_code,
        "retry_count": retry_count,
        "job_data": job_data,
        "timestamp": time.time(),
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    r.lpush("dlq:jobs", entry)
    logger.warning("pushed_to_dlq job_id=%s error=%s retry_count=%d", job_id, error, retry_count)


def pop_from_dlq() -> dict[str, Any] | None:
    """Pop the oldest entry from the dead-letter queue (FIFO)."""
    from app.job_store import get_redis

    r = get_redis()
    raw = r.rpop("dlq:jobs")
    if raw is None:
        return None
    return json.loads(raw)


def dlq_length() -> int:
    """Return the number of entries in the dead-letter queue."""
    from app.job_store import get_redis

    return get_redis().llen("dlq:jobs")


def inspect_dlq(limit: int = 50) -> list[dict[str, Any]]:
    """Inspect DLQ entries without consuming them.

    Args:
        limit: Maximum entries to return.

    Returns:
        List of DLQ entry dicts, newest first.
    """
    from app.job_store import get_redis

    r = get_redis()
    raw = r.lrange("dlq:jobs", 0, limit - 1)
    return [json.loads(entry) for entry in raw]


def requeue_from_dlq(index: int = 0) -> dict[str, Any] | None:
    """Remove an entry from DLQ and return it for reprocessing.

    Args:
        index: List index to remove (0 = oldest).

    Returns:
        The removed entry, or None if empty/invalid index.
    """
    from app.job_store import get_redis

    r = get_redis()
    length = r.llen("dlq:jobs")
    if index < 0 or index >= length:
        return None
    # Use LINDEX + LREM to remove by index
    raw = r.lindex("dlq:jobs", index)
    if raw is None:
        return None
    r.lrem("dlq:jobs", 1, raw)
    return json.loads(raw)


def clear_dlq() -> int:
    """Clear all entries from the dead-letter queue. Returns count removed."""
    from app.job_store import get_redis

    r = get_redis()
    count = r.llen("dlq:jobs")
    r.delete("dlq:jobs")
    logger.info("dlq_cleared count=%d", count)
    return count
