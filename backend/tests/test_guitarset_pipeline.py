"""Tests for GuitarSet download/parse/CQT pipeline (Commit 101)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, ROOT_NOTES, CHORD_QUALITIES
from scripts.parse_guitarset import (
    _strip_extensions,
    _parse_jams_chord_label,
    _normalize_quality,
    parse_guitarset_jams,
    save_timelines,
)
from scripts.extract_guitarset_cqt import (
    _extract_cqt,
    _frame_labels_from_timeline,
    _build_windows,
    process_song,
    PLAYER_SPLIT,
    HOP_SEC,
    WINDOW,
    FEATURE_DIM,
    N_CHORD_IDX,
)


# ---------------------------------------------------------------------------
# parse_guitarset unit tests
# ---------------------------------------------------------------------------

class TestStripExtensions:
    def test_removes_parenthesized(self):
        assert _strip_extensions("C:maj7(#11)") == "C:maj7"

    def test_removes_bass_note(self):
        assert _strip_extensions("C:maj/E") == "C:maj"

    def test_removes_both(self):
        assert _strip_extensions("G:7(b9,b13)/D") == "G:7"

    def test_no_extension(self):
        assert _strip_extensions("C:maj") == "C:maj"

    def test_bare_root(self):
        assert _strip_extensions("C") == "C"

    def test_no_chord(self):
        assert _strip_extensions("N") == "N"
        assert _strip_extensions("N") is not None


class TestNormalizeQuality:
    def test_major_shorthand(self):
        assert _normalize_quality("") == "maj"

    def test_minor_shorthand(self):
        assert _normalize_quality("m") == "min"

    def test_m7_to_min7(self):
        assert _normalize_quality("m7") == "min7"

    def test_m9_to_min9(self):
        assert _normalize_quality("m9") == "min9"

    def test_hdim7_stays(self):
        assert _normalize_quality("hdim7") == "hdim7"

    def test_minmaj7_stays(self):
        assert _normalize_quality("minmaj7") == "minmaj7"

    def test_known_quality_passthrough(self):
        for q in ["maj", "min", "7", "dim7", "aug"]:
            assert _normalize_quality(q) == q, f"Failed for {q}"


class TestParseJamsChordLabel:
    def test_major(self):
        assert _parse_jams_chord_label("C:maj") == "C:maj"

    def test_minor(self):
        assert _parse_jams_chord_label("D:min") == "D:min"

    def test_dominant_7(self):
        assert _parse_jams_chord_label("G:7") == "G:7"

    def test_shorthand_root_only(self):
        assert _parse_jams_chord_label("C") == "C:maj"

    def test_minor_shorthand(self):
        assert _parse_jams_chord_label("Am") == "A:min"

    def test_hdim7_mapped_to_dim7(self):
        assert _parse_jams_chord_label("B:hdim7") == "B:dim7"

    def test_minmaj7_mapped_to_maj7(self):
        assert _parse_jams_chord_label("C:minmaj7") == "C:maj7"

    def test_no_chord_label(self):
        assert _parse_jams_chord_label("N") is None

    def test_with_alterations(self):
        assert _parse_jams_chord_label("E:7(b9,#9)") == "E:7"

    def test_with_bass_note(self):
        assert _parse_jams_chord_label("C:maj/E") == "C:maj"


class TestParseGuitarSetJams:
    def _make_jams(self, chords: list[tuple[float, float, str]]) -> dict:
        """Create a minimal JAMS file structure."""
        return {
            "annotations": [{
                "namespace": "chord",
                "annotation_metadata": {"corpus": "GuitarSet"},
                "data": [
                    {"time": start, "duration": end - start, "value": label}
                    for start, end, label in chords
                ],
            }],
            "sandbox": {},
        }

    def test_parses_valid_chords(self, tmp_path):
        jams_data = self._make_jams([
            (0.0, 2.0, "C:maj"),
            (2.0, 4.0, "G:7"),
        ])
        jf = tmp_path / "00_BN1-129-Eb_comp.jams"
        with open(jf, "w") as f:
            json.dump(jams_data, f)

        songs = parse_guitarset_jams(tmp_path)
        assert "00_BN1-129-Eb_comp" in songs
        assert len(songs["00_BN1-129-Eb_comp"]) == 2

    def test_skips_no_chord(self, tmp_path):
        jams_data = self._make_jams([
            (0.0, 1.0, "N"),
            (1.0, 2.0, "C:maj"),
        ])
        jf = tmp_path / "test.jams"
        with open(jf, "w") as f:
            json.dump(jams_data, f)

        songs = parse_guitarset_jams(tmp_path)
        assert len(songs["test"]) == 1
        assert songs["test"][0]["chord"] == "C:maj"

    def test_maps_hdim7(self, tmp_path):
        jams_data = self._make_jams([
            (0.0, 2.0, "B:hdim7"),
        ])
        jf = tmp_path / "test.jams"
        with open(jf, "w") as f:
            json.dump(jams_data, f)

        songs = parse_guitarset_jams(tmp_path)
        assert songs["test"][0]["chord"] == "B:dim7"

    def test_save_timelines(self, tmp_path):
        songs = {
            "track_01": [{"start": 0.0, "end": 2.0, "chord": "C:maj"}],
        }
        out_dir = tmp_path / "timelines"
        save_timelines(songs, out_dir)

        saved = json.loads((out_dir / "track_01.json").read_text())
        assert len(saved) == 1
        assert saved[0]["chord"] == "C:maj"


# ---------------------------------------------------------------------------
# extract_guitarset_cqt unit tests
# ---------------------------------------------------------------------------

class TestFrameLabelsFromTimeline:
    def test_single_chord(self):
        timeline = [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]
        num_frames = 10
        labels = _frame_labels_from_timeline(timeline, num_frames)
        assert labels[0] == CHORD_TO_IDX["C:maj"]
        assert labels[9] == CHORD_TO_IDX["C:maj"]  # frame 9 (0.9s) is within chord (0.0-1.0s)

    def test_chord_change(self):
        timeline = [
            {"start": 0.0, "end": 0.5, "chord": "C:maj"},
            {"start": 0.5, "end": 1.0, "chord": "G:7"},
        ]
        num_frames = 10
        labels = _frame_labels_from_timeline(timeline, num_frames)
        assert labels[0] == CHORD_TO_IDX["C:maj"]
        # Frame 5 (0.5s) is boundary — forward bias to G:7
        assert labels[5] == CHORD_TO_IDX["G:7"]

    def test_no_chord_gap(self):
        timeline = [
            {"start": 0.0, "end": 0.3, "chord": "C:maj"},
        ]
        num_frames = 10
        labels = _frame_labels_from_timeline(timeline, num_frames)
        assert labels[0] == CHORD_TO_IDX["C:maj"]
        assert labels[4] == N_CHORD_IDX  # frame 0.4s is beyond chord

    def test_empty_timeline(self):
        timeline = []
        labels = _frame_labels_from_timeline(timeline, 10)
        assert np.all(labels == N_CHORD_IDX)


class TestBuildWindows:
    def test_window_shape(self):
        T = 200
        features = np.random.randn(T, FEATURE_DIM).astype(np.float32)
        labels = np.random.randint(0, 10, size=T).astype(np.int32)
        windows, window_labels = _build_windows(features, labels)

        expected_overlap = (T + 64 - 1) // 64
        assert windows.shape == (expected_overlap, WINDOW, FEATURE_DIM)
        assert window_labels.shape == (expected_overlap,)

    def test_center_frame_label(self):
        features = np.zeros((200, FEATURE_DIM), dtype=np.float32)
        labels = np.full(200, N_CHORD_IDX, dtype=np.int32)
        # First window's center maps to original frame index 0
        labels[0] = 5
        _, window_labels = _build_windows(features, labels)
        assert window_labels[0] == 5


class TestExtractCqt:
    def test_output_shape(self):
        sr = 44100
        y = np.random.randn(sr * 2) * 0.01  # 2 seconds of noise
        features = _extract_cqt(y, sr)
        expected_frames = len(y) // int(sr * HOP_SEC)
        assert features.shape[1] == FEATURE_DIM
        assert abs(features.shape[0] - expected_frames) <= 1

    def test_normalization(self):
        sr = 44100
        y = np.random.randn(sr * 1) * 0.01
        features = _extract_cqt(y, sr)
        # CQT portion (first 36 bins) should sum to ~1 per frame
        cqt_part = features[:, :36]
        row_sums = cqt_part.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=0.15), f"cqt sums: {row_sums}"
        # Bass channel (last 4 bins) should have reasonable values
        bass_part = features[:, 36:]
        assert bass_part.min() >= 0


class TestPlayerSplit:
    def test_all_players_have_split(self):
        for pid in ["00", "01", "02", "03"]:
            assert PLAYER_SPLIT[pid] == "train"
        assert PLAYER_SPLIT["04"] == "val"
        assert PLAYER_SPLIT["05"] == "test"


# ---------------------------------------------------------------------------
# Integration tests (using synthetic audio)
# ---------------------------------------------------------------------------

class TestProcessSongMock:
    def test_process_synthetic_song(self, tmp_path):
        """Process a tiny synthetic song and verify the output .npz."""
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration))

        # Create a simple sine wave
        y = np.sin(2 * np.pi * 440 * t) * 0.1
        audio_path = tmp_path / "00_BN1-129-Eb_comp.wav"
        import soundfile as sf
        sf.write(str(audio_path), y, sr)

        # Create timeline
        timeline = [
            {"start": 0.0, "end": 1.5, "chord": "C:maj"},
            {"start": 1.5, "end": 3.0, "chord": "G:7"},
        ]
        timeline_path = tmp_path / "timelines" / "00_BN1-129-Eb_comp.json"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timeline_path, "w") as f:
            json.dump(timeline, f)

        cqt_dir = tmp_path / "cqt"
        result = process_song(audio_path, timeline_path, cqt_dir, force=True)

        assert result is not None
        assert result["track_id"] == "00_BN1-129-Eb_comp"
        assert result["split"] == "train"

        # Check saved .npz
        npz_path = cqt_dir / "00_BN1-129-Eb_comp.npz"
        assert npz_path.exists()
        data = np.load(npz_path)
        assert "features" in data
        assert "labels" in data
        assert "player_id" in data
        assert str(data["player_id"]) == "00"
        assert str(data["split"]) == "train"

    def test_caching_no_force(self, tmp_path):
        """Verify that existing .npz is not re-processed."""
        sr = 44100
        y = np.random.randn(sr * 1) * 0.01
        audio_path = tmp_path / "01_test_song.wav"
        import soundfile as sf
        sf.write(str(audio_path), y, sr)

        timeline = [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]
        timeline_path = tmp_path / "timelines" / "01_test_song.json"
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(timeline_path, "w") as f:
            json.dump(timeline, f)

        cqt_dir = tmp_path / "cqt"
        result1 = process_song(audio_path, timeline_path, cqt_dir, force=True)
        result2 = process_song(audio_path, timeline_path, cqt_dir, force=False)
        assert result2["status"] == "cached"
