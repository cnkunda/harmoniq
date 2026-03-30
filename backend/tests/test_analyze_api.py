"""HTTP tests for in-memory analyze API (PRIORITIES §3)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app, jobs

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    jobs.clear()
    yield
    jobs.clear()


def test_post_analyze_returns_job_id():
    r = client.post("/analyze", json={"url": "https://www.youtube.com/watch?v=stub"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "job_id" in data
    uuid.UUID(data["job_id"])  # raises if invalid


def test_get_analyze_complete_with_stub_lesson():
    job_id = client.post("/analyze", json={"url": None}).json()["job_id"]
    r = client.get(f"/analyze/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "complete"
    assert body["error"] is None
    assert body["result"] is not None
    assert body["result"]["job_id"] == job_id
    assert body["result"]["song_title"] == "Stub Song"


def test_get_analyze_unknown_job_returns_404_json():
    missing = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/analyze/{missing}")
    assert r.status_code == 404, r.text
    err = r.json()
    assert "detail" in err
    assert missing in err["detail"]
