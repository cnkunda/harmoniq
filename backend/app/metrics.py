"""Prometheus metrics for Harmoniq.

Exposes counters, histograms, and gauges for:
- Job lifecycle (total, duration, errors)
- Pipeline stage timing
- HTTP request latency
- Redis health
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    REGISTRY,
)

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


def metrics_response() -> bytes:
    """Generate Prometheus metrics text format."""
    return generate_latest(REGISTRY)
