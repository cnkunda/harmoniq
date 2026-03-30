"""HTTP tests for in-memory analyze API (PRIORITIES §3)."""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.jobs import ANALYSIS_FAILED_USER_MESSAGE, jobs
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    jobs.clear()
    yield
    jobs.clear()


def _poll_until_not_processing(job_id: str, *, timeout_seconds: float = 5.0) -> dict:
    start = time.time()
    last: dict | None = None
    while True:
        assert time.time() - start < timeout_seconds, (
            f"Timed out waiting for job {job_id} to finish; last={last}"
        )
        r = client.get(f"/analyze/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        last = body
        if body["status"] != "processing":
            return body
        time.sleep(0.1)


def test_post_analyze_returns_job_id():
    r = client.post("/analyze", json={"url": "https://www.youtube.com/watch?v=stub"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "job_id" in data
    uuid.UUID(data["job_id"])  # raises if invalid


def test_get_analyze_processing_then_complete_with_stub_lesson():
    job_id = client.post("/analyze", json={"url": None}).json()["job_id"]
    r = client.get(f"/analyze/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processing"
    body = _poll_until_not_processing(job_id)
    assert body["status"] == "complete"
    assert body["error"] is None
    assert body["result"] is not None
    assert body["result"]["job_id"] == job_id
    assert body["result"]["song_title"] == "Stub Song"


def test_worker_forced_exception_surfaces_as_failed_with_user_safe_message():
    job_id = client.post("/analyze", json={"url": "force_error"}).json()["job_id"]
    r = client.get(f"/analyze/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processing"

    body = _poll_until_not_processing(job_id)
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"] == ANALYSIS_FAILED_USER_MESSAGE


def test_get_analyze_unknown_job_returns_404_json():
    missing = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/analyze/{missing}")
    assert r.status_code == 404, r.text
    err = r.json()
    assert "detail" in err
    assert missing in err["detail"]
