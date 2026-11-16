"""Commit 16: job runtime contract, health signal, and restart retention."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import JobStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    from app.jobs import coach_hydration, jobs

    jobs.clear()
    coach_hydration.clear()
    yield
    jobs.clear()
    coach_hydration.clear()


@pytest.fixture
def redis_ok(monkeypatch):
    monkeypatch.setattr("app.job_store.ping", lambda: True)


def test_health_reports_celery_runtime(monkeypatch, redis_ok):
    monkeypatch.delenv("HARMONIQ_SKIP_CELERY", raising=False)

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["job_runtime"] == "celery"
    assert body["job_runtime_fallback"] == ""


def test_health_flags_thread_fallback(monkeypatch, redis_ok):
    monkeypatch.setenv("HARMONIQ_SKIP_CELERY", "1")

    body = client.get("/health").json()

    assert body["status"] == "degraded"
    assert body["job_runtime"] == "thread"
    assert body["job_runtime_fallback"] == "HARMONIQ_SKIP_CELERY=1"


def test_processing_job_restart_reloads_status_without_redispatch(monkeypatch):
    """API restart reloads the status row but never resumes execution.

    With the thread fallback the in-flight work died with the API process.
    With Celery the worker owns execution and is unaffected by an API restart.
    """
    from app import jobs as jobs_mod

    stored = JobStatus(
        status="processing",
        result=None,
        error=None,
        progress=0.5,
        stage_label="Separating stems…",
    )
    monkeypatch.setattr("app.repository.list_active_jobs", lambda: [("job-restart", stored)])

    with patch("app.jobs.enqueue_analyze_job") as enqueue:
        loaded = jobs_mod.load_jobs_from_db()

    assert loaded == 1
    assert jobs_mod.jobs["job-restart"].status == "processing"
    enqueue.assert_not_called()
