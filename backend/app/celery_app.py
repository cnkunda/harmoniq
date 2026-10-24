from __future__ import annotations

import logging
import os

from celery import Celery

logger = logging.getLogger("harmoniq.celery")

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery(
    "harmoniq",
    broker=broker_url,
    backend=result_backend,
)

from kombu import Queue

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    task_track_started=True,
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    task_time_limit=900,
    task_soft_time_limit=600,
    task_queues=(
        Queue("celery", max_priority=10),
        Queue("analyze.urgent", max_priority=10),
        Queue("analyze.normal", max_priority=10),
        Queue("analyze.low", max_priority=10),
    ),
    task_default_queue="analyze.normal",
    task_queue_max_priority=10,
    broker_transport_options={
        "priority_steps": [0, 3, 6, 9],
        "queue_order_strategy": "priority",
    },
)

app.autodiscover_tasks(["app.tasks"], force=True)


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Schedule periodic cleanup tasks (runs on the celery beat schedule)."""
    # Currently no periodic tasks — placeholder for future cleanup.
    pass


def on_worker_process_init(**kwargs):
    """Initialize database connection pool in each worker process."""
    try:
        from app.db import init_db as _init_db
        _init_db()
        logger.info("Worker process: database initialized")
    except Exception:
        logger.warning("Worker process: database not available")
