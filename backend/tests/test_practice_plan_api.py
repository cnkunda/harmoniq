"""POST /practice/plan merges device `library_lessons` when in-memory jobs are empty."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.jobs import jobs
from app.main import app
from app.schemas import DrillSlot, LessonJSON, LessonSectionStub, PracticePlan

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


def test_practice_plan_api_tired_mood_shorter_without_technique(monkeypatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_PRACTICE_PLAN", "1")
    jobs.clear()
    try:
        la = _lesson(job_id="job-a", style="rock", section_tags=["bend"])
        lb = _lesson(job_id="job-b", style="rock", section_tags=["vibrato"])
        standard = client.post(
            "/practice/plan",
            json={
                "player_profile": {"weak_areas": ["bending"]},
                "job_ids": ["job-a", "job-b"],
                "library_lessons": [la.model_dump(mode="json"), lb.model_dump(mode="json")],
                "duration_minutes": 25,
            },
        )
        tired = client.post(
            "/practice/plan",
            json={
                "player_profile": {"weak_areas": ["bending"]},
                "job_ids": ["job-a", "job-b"],
                "library_lessons": [la.model_dump(mode="json"), lb.model_dump(mode="json")],
                "duration_minutes": 25,
                "mood": "tired",
            },
        )
        assert standard.status_code == 200, standard.text
        assert tired.status_code == 200, tired.text
        s_data = standard.json()
        t_data = tired.json()
        assert t_data["total_duration_seconds"] < s_data["total_duration_seconds"]
        assert [s["slot_type"] for s in t_data["slots"]] == ["warmup", "song_section", "free_jam"]
    finally:
        jobs.clear()
        monkeypatch.delenv("HARMONIQ_SKIP_PRACTICE_PLAN", raising=False)


def _adapt_plan_json() -> dict:
    slots = [
        DrillSlot(
            slot_id="slot-a",
            slot_type="technique",
            duration_seconds=240,
            title="Bending drill",
            difficulty=2,
        ),
        DrillSlot(
            slot_id="slot-b",
            slot_type="free_jam",
            duration_seconds=300,
            title="Free jam",
            difficulty=2,
        ),
    ]
    return PracticePlan(
        plan_id="plan-api",
        slots=slots,
        total_duration_seconds=540,
    ).model_dump(mode="json")


def test_session_plan_adapt_returns_remediation() -> None:
    res = client.post(
        "/session/plan/adapt",
        json={
            "plan": _adapt_plan_json(),
            "slot_index": 0,
            "slot_performance": {
                "slot_id": "slot-a",
                "slot_type": "technique",
                "title": "Bending drill",
                "accuracy": 0.3,
                "timing": 0.7,
                "confidence": "high",
                "completion": True,
            },
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["next_slot_index"] == 1
    assert data["adaptation"]["action"] == "insert_remediation"
    assert data["plan"]["slots"][1]["intent"] == "remediation"
    assert data["plan"]["slots"][1]["remediation_for_slot_id"] == "slot-a"
    assert data["slot_result"]["slot_id"] == "slot-a"


def test_session_plan_adapt_rejects_bad_index() -> None:
    res = client.post(
        "/session/plan/adapt",
        json={
            "plan": _adapt_plan_json(),
            "slot_index": 4,
            "slot_performance": {
                "slot_id": "slot-a",
                "slot_type": "technique",
                "title": "Bending drill",
                "completion": True,
            },
        },
    )
    assert res.status_code == 400
