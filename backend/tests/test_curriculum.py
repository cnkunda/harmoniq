from __future__ import annotations

from fastapi.testclient import TestClient

from app.jobs import jobs
from app.main import app
from app.schemas import JobStatus, LessonJSON

client = TestClient(app)


def _lesson(job_id: str, *, style: str, techniques: list[str], title: str) -> LessonJSON:
    return LessonJSON(
        job_id=job_id,
        song_title=title,
        artist="Fixture Artist",
        style_label=style,
        tempo=108.0,
        sections=[{"label": "A", "technique_tags": techniques}],
    )


def test_curriculum_ranks_bending_blues_first():
    jobs.clear()
    try:
        jobs["job_blues_bend"] = JobStatus(
            status="complete",
            result=_lesson("job_blues_bend", style="blues", techniques=["bend"], title="Blue Bend"),
            error=None,
        )
        jobs["job_country_pick"] = JobStatus(
            status="complete",
            result=_lesson("job_country_pick", style="country", techniques=["alternate-picking"], title="Chicken Pick"),
            error=None,
        )
        jobs["job_blues_vibrato"] = JobStatus(
            status="complete",
            result=_lesson("job_blues_vibrato", style="blues", techniques=["vibrato"], title="Blue Vibrato"),
            error=None,
        )

        res = client.post(
            "/curriculum/suggest",
            json={
                "player_profile": {
                    "weak_areas": ["bending"],
                    "skill_nodes": [{"id": "bend_accuracy", "score": 0.35}],
                },
                "job_ids": ["job_blues_bend", "job_country_pick", "job_blues_vibrato"],
            },
        )
        assert res.status_code == 200, res.text
        ranked = res.json()["ranked"]
        assert len(ranked) >= 2
        assert ranked[0]["job_id"] == "job_blues_bend"
        assert ranked[0]["technique_focus"].lower().startswith("bend")
        assert "weak area" in ranked[0]["reason_label"].lower()
    finally:
        jobs.clear()


def test_curriculum_skip_env_returns_empty(monkeypatch):
    monkeypatch.setenv("HARMONIQ_SKIP_CURRICULUM", "1")
    try:
        res = client.post("/curriculum/suggest", json={"player_profile": {"weak_areas": ["bending"]}, "job_ids": ["x"]})
        assert res.status_code == 200, res.text
        assert res.json()["ranked"] == []
    finally:
        monkeypatch.delenv("HARMONIQ_SKIP_CURRICULUM", raising=False)
