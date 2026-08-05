"""Celery application configuration for Harmoniq.

Broker: Redis (same instance as job_store, different DB index).
Result backend: Redis (DB 2).

Usage:
    from app.queue import celery_app
    celery_app.conf.update(...)
"""

from __future__ import annotations

import os

from celery import Celery

_broker_url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
_result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "harmoniq",
    broker=_broker_url,
    backend=_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Retry policy for transient broker failures
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=5,
    # Task time limits (prevent runaway tasks)
    task_soft_time_limit=600,  # 10 min soft limit
    task_time_limit=900,  # 15 min hard limit
)

# Auto-discover tasks in the app package
celery_app.autodiscover_tasks(["app"])
