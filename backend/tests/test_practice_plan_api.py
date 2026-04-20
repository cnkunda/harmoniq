"""POST /practice/plan merges device `library_lessons` when in-memory jobs are empty."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.jobs import jobs
from app.main import app
from app.schemas import LessonJSON, LessonSectionStub

client = TestClient(app)


def _lesson(*, job_id: str, style: str, section_tags: list[str]) -> LessonJSON:
    return LessonJSON(
        job_id=job_id,
        song_title=f"Title-{job_id}",
        artist="Fixture Artist",
        style_label=style,
        tempo=100.0,
        sections=[
            LessonSectionStub.model_validate(
                {"label": "Intro", "confidence": 0.75, "technique_tags": section_tags},
            )
        ],
    )


def test_practice_plan_uses_embedded_library_when_jobs_empty(monkeypatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_PRACTICE_PLAN", "1")
    jobs.clear()
    try:
        la = _lesson(job_id="job-a", style="rock", section_tags=["bend"])
        lb = _lesson(job_id="job-b", style="rock", section_tags=["vibrato"])
        res = client.post(
            "/practice/plan",
            json={
                "player_profile": {"weak_areas": ["bending"]},
                "job_ids": ["job-a", "job-b"],
                "library_lessons": [la.model_dump(mode="json"), lb.model_dump(mode="json")],
                "duration_minutes": 25,
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        types = [s["slot_type"] for s in data["slots"]]
        assert types == ["warmup", "technique", "song_section", "free_jam"]
        song = data["slots"][2]
        assert song["lesson_ref"] in {"job-a", "job-b"}
        assert song["slot_type"] == "song_section"
    finally:
        jobs.clear()
        monkeypatch.delenv("HARMONIQ_SKIP_PRACTICE_PLAN", raising=False)


def test_practice_plan_empty_jobs_and_no_embedded_yields_two_slots(monkeypatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_PRACTICE_PLAN", "1")
    jobs.clear()
    try:
        res = client.post(
            "/practice/plan",
            json={
                "player_profile": {"weak_areas": ["bending"]},
                "job_ids": ["missing-a", "missing-b"],
                "library_lessons": [],
                "duration_minutes": 25,
            },
        )
        assert res.status_code == 200, res.text
        types = [s["slot_type"] for s in res.json()["slots"]]
        assert types == ["warmup", "free_jam"]
    finally:
        jobs.clear()
        monkeypatch.delenv("HARMONIQ_SKIP_PRACTICE_PLAN", raising=False)
