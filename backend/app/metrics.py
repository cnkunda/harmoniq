"""Prometheus metrics for Harmoniq.

Exposes counters, histograms, and gauges for:
- Job lifecycle (total, duration, errors)
- Pipeline stage timing
- HTTP request latency
- Redis health
"""

from __future__ import annotations

import logging
import subprocess
import time
from contextlib import contextmanager
from typing import Generator

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    REGISTRY,
)

logger = logging.getLogger("harmoniq.metrics")

# ---------------------------------------------------------------------------
# Job metrics
# ---------------------------------------------------------------------------

jobs_total = Counter(
    "harmoniq_jobs_total",
    "Total number of analysis jobs",
    ["status", "stage"],
)

job_duration_seconds = Histogram(
    "harmoniq_job_duration_seconds",
    "Duration of analysis jobs in seconds",
    ["stage"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 900),
)

job_errors_total = Counter(
    "harmoniq_job_errors_total",
    "Total number of job errors",
    ["error_code"],
)

jobs_in_progress = Gauge(
    "harmoniq_jobs_in_progress",
    "Number of jobs currently processing",
)

# ---------------------------------------------------------------------------
# Queue / DLQ metrics (Commit 170)
# ---------------------------------------------------------------------------

queue_depth = Gauge(
    "harmoniq_queue_depth",
    "Number of jobs queued in a Celery queue",
    ["queue"],
)

dlq_length_gauge = Gauge(
    "harmoniq_dlq_length",
    "Number of jobs in the dead-letter queue",
)

# ---------------------------------------------------------------------------
# GPU metrics (Commit 170)
# ---------------------------------------------------------------------------

gpu_utilization_percent = Gauge(
    "harmoniq_gpu_utilization_percent",
    "GPU utilization percentage",
    ["gpu"],
)

gpu_memory_used_bytes = Gauge(
    "harmoniq_gpu_memory_used_bytes",
    "GPU memory used in bytes",
    ["gpu"],
)

gpu_memory_total_bytes = Gauge(
    "harmoniq_gpu_memory_total_bytes",
    "GPU memory total in bytes",
    ["gpu"],
)

# ---------------------------------------------------------------------------
# Pipeline stage metrics
# ---------------------------------------------------------------------------

pipeline_stage_duration_seconds = Histogram(
    "harmoniq_pipeline_stage_duration_seconds",
    "Duration of individual pipeline stages in seconds",
    ["stage"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "harmoniq_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "harmoniq_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# ---------------------------------------------------------------------------
# Redis health
# ---------------------------------------------------------------------------

redis_healthy = Gauge(
    "harmoniq_redis_healthy",
    "Whether Redis is reachable (1=healthy, 0=unhealthy)",
)

# ---------------------------------------------------------------------------
# Context managers for timing
# ---------------------------------------------------------------------------


@contextmanager
def track_stage(stage: str) -> Generator[None, None, None]:
    """Context manager that records the duration of a pipeline stage."""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        pipeline_stage_duration_seconds.labels(stage=stage).observe(duration)


@contextmanager
def track_job(job_id: str, stage: str) -> Generator[None, None, None]:
    """Context manager that records job-level timing and counts."""
    start = time.time()
    try:
        yield
        duration = time.time() - start
        job_duration_seconds.labels(stage=stage).observe(duration)
        jobs_total.labels(status="complete", stage=stage).inc()
    except Exception:
        duration = time.time() - start
        job_duration_seconds.labels(stage=stage).observe(duration)
        raise


# GPU metric cache (avoid running nvidia-smi on every scrape)
_gpu_cache: dict = {"ts": 0.0, "rows": []}
_GPU_CACHE_TTL = 10.0


def _collect_gpu_rows() -> list[dict]:
    """Run nvidia-smi and parse GPU rows. Returns [] on CPU-only hosts."""
    now = time.time()
    if now - _gpu_cache["ts"] < _GPU_CACHE_TTL and _gpu_cache["rows"] is not None:
        return _gpu_cache["rows"]
    rows: list[dict] = []
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            rows.append(
                {
                    "index": parts[0],
                    "util": float(parts[1]),
                    "mem_used": float(parts[2]) * 1024 * 1024,
                    "mem_total": float(parts[3]) * 1024 * 1024,
                }
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, OSError):
        rows = []
    except Exception:
        rows = []
    _gpu_cache["ts"] = now
    _gpu_cache["rows"] = rows
    return rows


def update_gpu_metrics() -> None:
    """Refresh GPU gauges; graceful no-op when CUDA/nvidia-smi unavailable."""
    try:
        rows = _collect_gpu_rows()
    except Exception:
        rows = []
    for row in rows:
        gpu = str(row["index"])
        try:
            gpu_utilization_percent.labels(gpu=gpu).set(row["util"])
            gpu_memory_used_bytes.labels(gpu=gpu).set(row["mem_used"])
            gpu_memory_total_bytes.labels(gpu=gpu).set(row["mem_total"])
        except Exception:
            logger.debug("gpu metric update failed", exc_info=True)


_KNOWN_QUEUES = ["celery", "analyze.urgent", "analyze.normal", "analyze.low"]
# Kombu's Redis transport stores each priority bucket in a separate list named
# ``<queue>\x06\x16<priority>`` (the priority-0 bucket uses the bare queue name).
_QUEUE_PRIORITY_SEP = "\x06\x16"
_QUEUE_PRIORITY_STEPS = (0, 3, 6, 9)


def _queue_depth(r, queue: str) -> int:
    """Sum queue length across all Celery priority buckets."""
    total = 0
    for priority in _QUEUE_PRIORITY_STEPS:
        key = queue if priority == 0 else f"{queue}{_QUEUE_PRIORITY_SEP}{priority}"
        try:
            total += int(r.llen(key))
        except Exception:
            pass
    return total


def update_queue_metrics() -> None:
    """Refresh queue-depth and DLQ-length gauges from Redis."""
    try:
        from app.job_store import dlq_length as _dlq_len, get_redis

        r = get_redis()
        try:
            dlq_length_gauge.set(_dlq_len())
        except Exception:
            pass
        for q in _KNOWN_QUEUES:
            try:
                queue_depth.labels(queue=q).set(_queue_depth(r, q))
            except Exception:
                pass
    except Exception:
        logger.debug("queue metric update failed", exc_info=True)


def metrics_response() -> bytes:
    """Generate Prometheus metrics text format."""
    return generate_latest(REGISTRY)
