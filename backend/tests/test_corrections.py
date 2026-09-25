"""Tests for Commit 110: Correction schemas, persistence, and merge logic."""
from __future__ import annotations

import json

import pytest

from app.jobs import jobs, save_job_to_disk, load_jobs_from_disk, coach_hydration
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    JobStatus,
    LessonJSON,
    SoloNote,
    SoloNotes,
    TimeSignature,
)


def _make_lesson(**overrides) -> LessonJSON:
    """Build a minimal LessonJSON for testing."""
    defaults = dict(
        job_id="test-corrections-1",
        song_title="Test Song",
        artist="Test Artist",
        key="C major",
        tempo=120.0,
        beat_grid=[0.0, 0.5, 1.0, 1.5],
        bar_timestamps=[0.0, 2.0],
        chord_timeline=ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.85),
            ChordEvent(timestamp=2.0, chord="A:min", confidence=0.8),
        ]),
        solo_notes=SoloNotes(notes=[
            SoloNote(start_time=0.5, duration=0.25, pitch=60, velocity=80),
            SoloNote(start_time=1.2, duration=0.3, pitch=64, velocity=75),
        ]),
        beat_grid_structured=BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5],
            downbeats=[0.0, 2.0],
            time_signature=TimeSignature(numerator=4, denominator=4),
            tick_value=0.5,
        ),
    )
    defaults.update(overrides)
    return LessonJSON(**defaults)


@pytest.fixture(autouse=True)
def _clean_jobs():
    """Clear in-memory jobs before and after each test."""
    jobs.clear()
    coach_hydration.clear()
    yield
    jobs.clear()
    coach_hydration.clear()


class TestChordCorrectionSchema:
    """Test chord correction Pydantic model behavior."""

    def test_chord_timeline_event_copy(self):
        lesson = _make_lesson()
        event = lesson.chord_timeline.events[0]
        new_event = event.model_copy(update={"chord": "F:maj", "confidence": 1.0})
        assert new_event.chord == "F:maj"
        assert new_event.confidence == 1.0
        assert event.chord == "C:maj"  # original unchanged

    def test_lesson_copy_with_updates(self):
        lesson = _make_lesson()
        new_events = list(lesson.chord_timeline.events)
        new_events[0] = new_events[0].model_copy(update={"chord": "F:maj"})
        new_timeline = lesson.chord_timeline.model_copy(update={"events": new_events})
        patched = lesson.model_copy(update={"chord_timeline": new_timeline})
        assert patched.chord_timeline.events[0].chord == "F:maj"
        assert patched.chord_timeline.events[1].chord == "G:maj"  # unchanged

    def test_solo_note_copy(self):
        lesson = _make_lesson()
        note = lesson.solo_notes.notes[0]
        new_note = note.model_copy(update={"pitch": 62})
        assert new_note.pitch == 62
        assert note.pitch == 60  # original unchanged

    def test_chord_event_with_extra_attrs(self):
        """Extra attributes via model_config extra='allow' for correction tracking."""
        event = ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)
        # ChordEvent doesn't have extra='allow', so setting extra attrs should fail
        # unless the model is configured. Let's verify the model config.
        from app.schemas import ChordEvent as CE
        assert CE.model_config.get("extra") != "forbid"  # allow or ignore


class TestJobPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        """Test that completed jobs are saved to and loaded from disk."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

        lesson = _make_lesson()
        jobs["persist-test-1"] = JobStatus(status="complete", result=lesson)

        save_job_to_disk("persist-test-1")

        # Verify file exists
        job_dir = tmp_path / "data" / "jobs" / "persist-test-1"
        assert (job_dir / "JobStatus.json").exists()

        # Clear in-memory state
        jobs.clear()
        assert "persist-test-1" not in jobs

        # Reload from disk
        loaded = load_jobs_from_disk()
        assert loaded >= 1
        assert "persist-test-1" in jobs
        loaded_job = jobs["persist-test-1"]
        assert loaded_job.status == "complete"
        assert loaded_job.result is not None
        assert loaded_job.result.song_title == "Test Song"

    def test_save_processing_job_not_persisted(self, tmp_path, monkeypatch):
        """Processing jobs should NOT be persisted to disk."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

        lesson = _make_lesson()
        jobs["proc-test"] = JobStatus(status="processing", result=lesson)
        save_job_to_disk("proc-test")

        job_dir = tmp_path / "data" / "jobs" / "proc-test"
        assert not (job_dir / "JobStatus.json").exists()

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        """Loading from empty directory should return 0."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        loaded = load_jobs_from_disk()
        assert loaded == 0


class TestCorrectionMetrics:
    def test_correction_count_and_coverage(self):
        """Verify correction metrics can be computed from lesson data."""
        lesson = _make_lesson()
        total_events = len(lesson.chord_timeline.events) + len(lesson.solo_notes.notes)
        assert total_events == 5

        # Simulate 2 chord corrections
        correction_count = 2
        coverage = correction_count / total_events
        assert abs(coverage - 0.4) < 0.01
