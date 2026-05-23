"""Tests for user-supplied audio bridge (Commit 101 Phase 4)."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.user_audio_pipeline import (
    _parse_lab_label,
    process_pair,
    FEATURE_DIM,
    WINDOW,
)


class TestParseLabLabel:
    def test_major(self):
        assert _parse_lab_label("C:maj") == "C:maj"

    def test_shorthand_root(self):
        assert _parse_lab_label("C") == "C:maj"

    def test_shorthand_minor(self):
        assert _parse_lab_label("Am") == "A:min"

    def test_flat_root(self):
        assert _parse_lab_label("Bb:7") == "A#:7"

    def test_no_chord(self):
        assert _parse_lab_label("N") is None

    def test_with_alterations(self):
        assert _parse_lab_label("C:maj7(#11)") == "C:maj7"

    def test_hdim7_mapped(self):
        assert _parse_lab_label("B:hdim7") == "B:dim7"


class TestProcessPair:
    def test_processes_valid_pair(self, tmp_path):
        import soundfile as sf

        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t) * 0.1

        audio_path = tmp_path / "audio" / "test_song.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(audio_path), y, sr)

        lab_path = tmp_path / "labs" / "test_song.lab"
        lab_path.parent.mkdir(parents=True, exist_ok=True)
        lab_path.write_text(
            "0.0\t1.5\tC:maj\n1.5\t3.0\tG:7\n"
        )

        output_dir = tmp_path / "output"
        # process_pair saves to output_dir directly (not output_dir/cqt/)
        result = process_pair(audio_path, lab_path, output_dir)

        assert result is not None
        assert result["track_id"] == "test_song"

        npz_path = output_dir / "test_song.npz"
        assert npz_path.exists()

        data = np.load(npz_path)
        assert "features" in data
        assert "labels" in data
        assert data["features"].shape[1:] == (WINDOW, FEATURE_DIM)
        assert data["labels"].shape[0] == data["features"].shape[0]

    def test_skips_missing_lab(self, tmp_path):
        import soundfile as sf
        sr = 44100
        y = np.random.randn(sr).astype(np.float32) * 0.01
        audio_path = tmp_path / "audio" / "orphan.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(audio_path), y, sr)

        lab_path = tmp_path / "labs" / "orphan.lab"
        lab_path.parent.mkdir(parents=True, exist_ok=True)
        # Don't create the .lab file
        # process_pair should handle file-not-found gracefully

        output_dir = tmp_path / "output"
        result = process_pair(audio_path, lab_path, output_dir)
        # Should return None since lab file doesn't exist
        assert result is None

    def test_handles_bad_audio(self, tmp_path):
        bad_audio = tmp_path / "audio" / "bad.wav"
        bad_audio.parent.mkdir(parents=True, exist_ok=True)
        bad_audio.write_text("not audio data")

        lab_path = tmp_path / "labs" / "bad.lab"
        lab_path.parent.mkdir(parents=True, exist_ok=True)
        lab_path.write_text("0.0\t1.0\tC:maj\n")

        output_dir = tmp_path / "output"
        result = process_pair(bad_audio, lab_path, output_dir)
        assert result is None
