from __future__ import annotations

from fastapi.testclient import TestClient

from app.jobs import coach_hydration, jobs
from app.main import app
from app.schemas import CoachHydrationSection, CoachHydrationStatus, JobStatus, LessonJSON, LessonSectionStub

client = TestClient(app)


def test_get_coach_status_unknown_job_404():
    jobs.clear()
    coach_hydration.clear()
    r = client.get("/analyze/missing-job/coach")
    assert r.status_code == 404


def test_get_coach_status_pending_when_missing_hydration_entry():
    jobs.clear()
    coach_hydration.clear()
    jobs["job-1"] = JobStatus(
        status="complete",
        result=LessonJSON(job_id="job-1", sections=[LessonSectionStub(label="A")]),
        error=None,
    )
    r = client.get("/analyze/job-1/coach")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["sections"] == []


def test_get_coach_status_returns_fallback_payload():
    jobs.clear()
    coach_hydration.clear()
    jobs["job-2"] = JobStatus(
        status="complete",
        result=LessonJSON(job_id="job-2", sections=[LessonSectionStub(label="B")]),
        error=None,
    )
    coach_hydration["job-2"] = CoachHydrationStatus(
        status="fallback",
        fallback_reason="missing_api_key",
        sections=[CoachHydrationSection(index=0, coach_note="n", coach_explanation="e")],
    )
    r = client.get("/analyze/job-2/coach")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fallback"
    assert body["fallback_reason"] == "missing_api_key"
    assert body["sections"][0]["coach_note"] == "n"
