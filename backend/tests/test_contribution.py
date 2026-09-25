"""Tests for the user audio contribution pipeline (lab_export + contribute)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.chord_vocab import CHORD_TO_IDX
from app.lab_export import chord_timeline_to_lab
from app.schemas import ChordEvent, ChordTimeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timeline(chords: list[tuple[float, str]] | None = None) -> ChordTimeline:
    """Build a ChordTimeline from (timestamp, chord) pairs."""
    if chords is None:
        chords = [
            (0.0, "C:maj"),
            (1.0, "G:7"),
            (2.0, "A:min"),
            (3.0, "F:maj"),
        ]
    events = [ChordEvent(timestamp=t, chord=c, confidence=0.9) for t, c in chords]
    return ChordTimeline(events=events)


def _make_wav(path: Path, duration_sec: float = 5.0, sr: int = 22050) -> Path:
    """Write a minimal WAV file (silence) for testing."""
    import wave

    n_frames = int(duration_sec * sr)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * n_frames)
    return path


# ---------------------------------------------------------------------------
# lab_export tests
# ---------------------------------------------------------------------------

class TestLabExport:
    def test_basic_export(self):
        timeline = _make_timeline()
        lab = chord_timeline_to_lab(timeline)
        lines = lab.strip().split("\n")
        assert len(lines) == 4
        # First line: onset offset chord
        parts = lines[0].split("\t")
        assert parts[0] == "0.000"
        assert parts[1] == "1.000"
        assert parts[2] == "C:maj"

    def test_last_event_default_duration(self):
        timeline = _make_timeline([(0.0, "C:maj"), (2.0, "G:7")])
        lab = chord_timeline_to_lab(timeline)
        lines = lab.strip().split("\n")
        last_parts = lines[-1].split("\t")
        assert last_parts[0] == "2.000"
        assert last_parts[1] == "4.000"  # onset + 2.0 default

    def test_empty_timeline(self):
        timeline = ChordTimeline(events=[])
        lab = chord_timeline_to_lab(timeline)
        assert lab == ""

    def test_single_event(self):
        timeline = _make_timeline([(1.5, "D:min7")])
        lab = chord_timeline_to_lab(timeline)
        lines = lab.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split("\t")
        assert parts[0] == "1.500"
        assert parts[1] == "3.500"
        assert parts[2] == "D:min7"


# ---------------------------------------------------------------------------
# contribute validation tests
# ---------------------------------------------------------------------------

class TestContributionValidation:
    def test_no_chord_timeline(self):
        from app.contribute import ContributionError, _validate_contribution

        timeline = ChordTimeline(events=[])
        with pytest.raises(ContributionError, match="no_chord_timeline"):
            _validate_contribution(timeline, Path("/nonexistent"), "job1", {})

    def test_insufficient_annotations(self):
        from app.contribute import ContributionError, _validate_contribution

        timeline = _make_timeline([(0.0, "N"), (1.0, "N")])
        with pytest.raises(ContributionError, match="insufficient_annotations"):
            _validate_contribution(timeline, Path("/nonexistent"), "job1", {})

    def test_audio_not_found(self):
        from app.contribute import ContributionError, _validate_contribution

        timeline = _make_timeline()
        with pytest.raises(ContributionError, match="audio_not_found"):
            _validate_contribution(timeline, Path("/nonexistent/audio.wav"), "job1", {})

    def test_invalid_chord_label(self):
        from app.contribute import ContributionError, _validate_contribution

        timeline = _make_timeline([
            (0.0, "C:maj"), (1.0, "G:7"), (2.0, "A:min"), (3.0, "INVALID_CHORD"),
        ])
        wav_path = Path("/tmp/test.wav")
        with pytest.raises(ContributionError, match="invalid_chord_labels"):
            _validate_contribution(timeline, wav_path, "job1", {})

    def test_duplicate_contribution(self):
        from app.contribute import ContributionError, _validate_contribution

        timeline = _make_timeline()
        manifest = {"contributions": {"job1": {"track_id": "user_job1"}}}
        with pytest.raises(ContributionError, match="duplicate_contribution"):
            _validate_contribution(timeline, Path("/nonexistent"), "job1", manifest)


# ---------------------------------------------------------------------------
# contribute_audio integration test (mocked CQT extraction)
# ---------------------------------------------------------------------------

class TestContributeAudio:
    def test_successful_contribution(self, tmp_path):
        from app.contribute import contribute_audio

        # Create mock job directory with song.wav
        job_dir = tmp_path / "data" / "jobs" / "testjob"
        job_dir.mkdir(parents=True)
        wav_path = job_dir / "song.wav"
        _make_wav(wav_path, duration_sec=5.0)

        # Create contributed output directory
        contributed_dir = tmp_path / "data" / "user_contributed"
        contributed_dir.mkdir(parents=True)

        timeline = _make_timeline([(0.0, "C:maj"), (1.0, "G:7"), (2.0, "A:min"), (3.0, "F:maj")])

        with patch("app.contribute.get_data_dir", return_value=tmp_path / "data"), \
             patch("app.contribute.get_job_dir", return_value=job_dir), \
             patch("app.contribute.chord_timeline_to_lab", return_value="0.000\t1.000\tC:maj\n"), \
             patch("scripts.user_audio_pipeline.process_pair", return_value={"track_id": "user_testjob", "windows": 42}):
            result = contribute_audio(
                job_id="testjob",
                timeline=timeline,
                contributor_id="anon_test",
                license="cc-by-4.0",
            )

        assert result["status"] == "accepted"
        assert result["windows"] == 42
        assert result["track_id"] == "user_testjob"

        # Verify manifest was written
        manifest_path = contributed_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert "testjob" in manifest["contributions"]
        assert manifest["contributions"]["testjob"]["contributor_id"] == "anon_test"
