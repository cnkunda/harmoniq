"""Tests for frame-level chord supervision helpers (Chord 170)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_X_IDX,
    CHORD_TO_IDX_170,
    N_IDX_170,
)
from scripts.add_frame_labels import _frame_labels_for_meta, frame_times  # noqa: E402
from scripts.eval_chord_170 import aggregate_frame_probs  # noqa: E402


class TestFrameTimes:
    def test_geometry_matches_window_extractor(self):
        times = frame_times(np.array([0.0, 1.6]), window=16)
        assert times.shape == (2, 16)
        assert times[0, 0] == -0.8
        assert times[0, 7] == -0.1
        assert times[0, 8] == 0.0
        assert np.isclose(times[1, 8], 1.6)


class TestFrameLabels:
    def test_timeline_labels_every_frame(self, tmp_path):
        timeline = tmp_path / "timeline.json"
        timeline.write_text(json.dumps([
            {"start": 0.0, "end": 10.0, "chord": "C:maj"},
        ]))
        labels, bass = _frame_labels_for_meta(
            {"timeline": timeline}, np.array([0.0, 1.6]), window=16)
        assert labels.shape == (2, 16)
        assert np.all(labels[:, 8:] == CHORD_TO_IDX_170["C:maj"])
        assert np.all(labels[0, :8] == N_IDX_170)
        assert np.all(labels[1:] == CHORD_TO_IDX_170["C:maj"])
        assert np.all(bass == BASS_X_IDX)

    def test_notes_drive_chord_and_bass(self):
        notes = [(0.0, 10.0, 48.0), (0.0, 10.0, 52.0), (0.0, 10.0, 55.0)]
        labels, bass = _frame_labels_for_meta(
            {"notes": notes, "labels_from_notes": True},
            np.array([0.0]), window=16)
        assert np.all(labels[:, 8:] == CHORD_TO_IDX_170["C:maj"])
        assert np.all(bass[:, 8:] == BASS_TO_IDX["C"])

    def test_silence_is_no_chord(self):
        labels, bass = _frame_labels_for_meta(
            {"notes": [], "labels_from_notes": True},
            np.array([0.0]), window=16)
        assert np.all(labels == N_IDX_170)
        assert np.all(bass == BASS_X_IDX)


class TestFrameAggregation:
    def test_mean_over_frames(self):
        probs = np.array([[[0.2, 0.8], [0.6, 0.4]]], dtype=np.float32)
        agg = aggregate_frame_probs(probs)
        assert agg.shape == (1, 2)
        assert np.allclose(agg, [[0.4, 0.6]])

    def test_window_probs_unchanged(self):
        probs = np.array([[0.3, 0.7]], dtype=np.float32)
        assert np.array_equal(aggregate_frame_probs(probs), probs)
