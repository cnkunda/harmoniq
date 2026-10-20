"""Tests for Commit 159: structured user feedback, reversion, and exports."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.ingest import get_job_dir
from app.jobs import JobStatus, coach_hydration, jobs
from app.main import app
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    LessonJSON,
    SoloNote,
    SoloNotes,
    TimeSignature,
)

client = TestClient(app)


def _make_lesson(job_id: str) -> LessonJSON:
    return LessonJSON(
        job_id=job_id,
        song_title="Feedback Song",
        artist="Test Artist",
        key="C major",
        tempo=120.0,
        beat_grid=[0.0, 0.5, 1.0, 1.5],
        bar_timestamps=[0.0, 2.0],
        chord_timeline=ChordTimeline(
            events=[
                ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
                ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.85),
                ChordEvent(timestamp=2.0, chord="A:min", confidence=0.8),
            ]
        ),
        solo_notes=SoloNotes(
            notes=[
                SoloNote(start_time=0.5, duration=0.25, pitch=60, velocity=80),
                SoloNote(start_time=1.2, duration=0.3, pitch=64, velocity=75),
            ]
        ),
        beat_grid_structured=BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5],
            downbeats=[0.0, 2.0],
            time_signature=TimeSignature(numerator=4, denominator=4),
            tick_value=0.5,
        ),
    )


@pytest.fixture(autouse=True)
def _clean_jobs():
    jobs.clear()
    coach_hydration.clear()
    yield
    jobs.clear()
    coach_hydration.clear()


def _seed_job(job_id: str, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    lesson = _make_lesson(job_id)
    jobs[job_id] = JobStatus(status="complete", result=lesson)
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "BeatGrid.json").write_text(lesson.beat_grid_structured.model_dump_json(indent=2))
    (job_dir / "chordTimeline.json").write_text(lesson.chord_timeline.model_dump_json(indent=2))
    (job_dir / "SoloNotes.json").write_text(lesson.solo_notes.model_dump_json(indent=2))


class TestFeedbackSubmission:
    def test_chord_feedback_is_persisted(self, tmp_path, monkeypatch):
        job_id = "feedback-chord-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 1,
                "original_value": {"chord": "G:maj"},
                "corrected_value": {"chord": "G7"},
                "reason": "Dominant seventh",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["feedback_type"] == "chord_correction"
        assert body["event_index"] == 1
        assert body["corrected_value"] == {"chord": "G7"}
        assert body["job_id"] == job_id
        assert body["song_id"] == job_id
        assert body["reverted_at"] is None

        audit = json.loads((get_job_dir(job_id) / "feedback.json").read_text())
        assert len(audit) == 1
        assert audit[0]["id"] == body["id"]

    def test_note_feedback_is_persisted(self, tmp_path, monkeypatch):
        job_id = "feedback-note-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "note_correction",
                "event_index": 0,
                "original_value": {"pitch": 60, "duration": 0.25, "start_time": 0.5},
                "corrected_value": {"pitch": 62},
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["feedback_type"] == "note_correction"

    def test_wrong_chord_ignores_corrected_value(self, tmp_path, monkeypatch):
        job_id = "feedback-wrong-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "wrong_chord",
                "event_index": 2,
                "original_value": {"chord": "A:min"},
                "corrected_value": {"chord": "F:maj"},
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["corrected_value"] is None

    def test_invalid_event_index_is_rejected(self, tmp_path, monkeypatch):
        job_id = "feedback-invalid-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 99,
                "original_value": {"chord": "C:maj"},
                "corrected_value": {"chord": "D:maj"},
            },
        )
        assert r.status_code == 400

    def test_chord_correction_requires_replacement(self, tmp_path, monkeypatch):
        job_id = "feedback-missing-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
                "corrected_value": {},
            },
        )
        assert r.status_code == 400

    def test_unknown_job_returns_404(self):
        r = client.post(
            "/analyze/missing-job/feedback",
            json={
                "feedback_type": "wrong_chord",
                "event_index": 0,
                "original_value": {"chord": "C"},
            },
        )
        assert r.status_code == 404


class TestFeedbackExport:
    def test_chord_export_dedupes_and_excludes_notes(self, tmp_path, monkeypatch):
        job_id = "feedback-export-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
                "corrected_value": {"chord": "D:maj"},
            },
        ).status_code == 200
        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
                "corrected_value": {"chord": "E:maj"},
            },
        ).status_code == 200
        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "wrong_chord",
                "event_index": 2,
                "original_value": {"chord": "A:min"},
            },
        ).status_code == 200
        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "note_correction",
                "event_index": 0,
                "original_value": {"pitch": 60},
                "corrected_value": {"pitch": 62},
            },
        ).status_code == 200

        r = client.get(f"/analyze/{job_id}/feedback/export?split=chord")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["job_id"] == job_id
        assert body["split"] == "chord"
        assert len(body["records"]) == 2
        corrected = {record["event_index"]: record for record in body["records"]}
        assert corrected[0]["corrected_value"] == {"chord": "E:maj"}
        assert corrected[2]["feedback_type"] == "wrong_chord"
        assert all(record["feedback_type"] != "note_correction" for record in body["records"])

    def test_solo_export_contains_note_feedback(self, tmp_path, monkeypatch):
        job_id = "feedback-export-2"
        _seed_job(job_id, tmp_path, monkeypatch)

        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "note_correction",
                "event_index": 1,
                "original_value": {"pitch": 64},
                "corrected_value": {"pitch": 66},
            },
        ).status_code == 200
        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "wrong_chord",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
            },
        ).status_code == 200

        r = client.get(f"/analyze/{job_id}/feedback/export?split=solo")
        assert r.status_code == 200, r.text
        records = r.json()["records"]
        assert len(records) == 1
        assert records[0]["feedback_type"] == "note_correction"

    def test_invalid_split_is_rejected(self, tmp_path, monkeypatch):
        job_id = "feedback-export-3"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.get(f"/analyze/{job_id}/feedback/export?split=all")
        assert r.status_code == 400

    def test_revert_marks_record_and_removes_it_from_export(self, tmp_path, monkeypatch):
        job_id = "feedback-revert-1"
        _seed_job(job_id, tmp_path, monkeypatch)

        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "chord_correction",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
                "corrected_value": {"chord": "D:maj"},
            },
        ).status_code == 200

        r = client.post(
            f"/analyze/{job_id}/feedback/revert",
            json={"feedback_type": "chord_correction", "event_index": 0},
        )
        assert r.status_code == 200, r.text
        assert r.json()["reverted_at"] is not None

        export = client.get(f"/analyze/{job_id}/feedback/export?split=chord")
        assert export.status_code == 200
        assert export.json()["records"] == []

        audit = json.loads((get_job_dir(job_id) / "feedback.json").read_text())
        assert audit[0]["reverted_at"] is not None

    def test_double_revert_returns_409(self, tmp_path, monkeypatch):
        job_id = "feedback-revert-2"
        _seed_job(job_id, tmp_path, monkeypatch)

        assert client.post(
            f"/analyze/{job_id}/feedback",
            json={
                "feedback_type": "wrong_chord",
                "event_index": 0,
                "original_value": {"chord": "C:maj"},
            },
        ).status_code == 200
        payload = {"feedback_type": "wrong_chord", "event_index": 0}
        assert client.post(f"/analyze/{job_id}/feedback/revert", json=payload).status_code == 200
        assert client.post(f"/analyze/{job_id}/feedback/revert", json=payload).status_code == 409

    def test_revert_missing_feedback_returns_404(self, tmp_path, monkeypatch):
        job_id = "feedback-revert-3"
        _seed_job(job_id, tmp_path, monkeypatch)

        r = client.post(
            f"/analyze/{job_id}/feedback/revert",
            json={"feedback_type": "note_correction", "event_index": 0},
        )
        assert r.status_code == 404
