"""Tests for Commit 8 analyze_audio fallback observability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import analyze_audio


def test_librosa_failure_returns_fallback_and_records_metric(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded: list[tuple[str, str]] = []

    def _record(stage: str, reason: str = "exception") -> None:
        recorded.append((stage, reason))

    def _boom(_path: Path) -> None:
        raise RuntimeError("librosa exploded")

    monkeypatch.setattr(analyze_audio, "record_fallback", _record)
    monkeypatch.setattr(analyze_audio, "librosa_summarize", _boom)

    wav = tmp_path / "guitar.wav"
    wav.write_bytes(b"not real audio")

    lesson = analyze_audio.build_lesson_json_from_librosa(
        "job-fallback",
        guitar_stem_path=wav,
        vocals_stem_path=None,
        stems={"guitar": "jobs/job-fallback/stems/guitar.wav"},
        wav_path="jobs/job-fallback/song.wav",
    )

    assert lesson.job_id == "job-fallback"
    assert ("librosa_summary", "exception") in recorded
