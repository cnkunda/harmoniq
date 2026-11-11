"""Tests for the opt-in student tier in the fallback chain."""

from __future__ import annotations

from pathlib import Path

from app.mt3 import fallback
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    SoloNotes,
    TimeSignature,
)


def _beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
        beats=[0.0, 0.5, 1.0],
        downbeats=[0.0],
    )


class _FakeStudent:
    def __init__(self, *args, **kwargs):
        pass

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_path, beat_grid=None, include_solo=None):
        timeline = ChordTimeline(
            events=[
                ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.8),
                ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.7),
            ]
        )
        return timeline, SoloNotes(notes=[]), {"backend": "test"}


class TestStudentFallback:
    def test_disabled_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HARMONIQ_STUDENT_ENABLED", "0")
        audio = tmp_path / "x.wav"
        audio.write_bytes(b"")
        assert fallback._try_student(audio, _beat_grid()) is None

    def test_enabled_returns_student_result(self, monkeypatch, tmp_path):
        import app.student.inference as inference

        monkeypatch.setenv("HARMONIQ_STUDENT_ENABLED", "1")
        monkeypatch.setattr(inference, "student_enabled", lambda: True)
        monkeypatch.setattr(inference, "StudentModel", _FakeStudent)

        audio = tmp_path / "x.wav"
        audio.write_bytes(b"")
        result = fallback._try_student(audio, _beat_grid())
        assert result is not None
        assert result.source == "student"
        assert len(result.chord_timeline.events) == 2
        assert result.mean_confidence > 0.0

    def test_label_is_registered(self):
        label = fallback.get_transcription_source_label("student")
        assert "student" in label.lower()
