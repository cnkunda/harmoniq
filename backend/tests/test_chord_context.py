"""Tests for long-context chord helpers (Chord 170)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import BASS_X_IDX, CHORD_TO_IDX_170, N_IDX_170  # noqa: E402
from scripts.chord_context import (  # noqa: E402
    PITCH_TARGET_TABLE,
    build_segment_index,
    context_batch,
    context_for_window,
    inversion_from_chord_bass,
    pitch_targets_from_chords,
    root_quality_from_chords,
    structured_decode,
)
from scripts.eval_chord_170 import (  # noqa: E402
    macro_f1_min_support,
    support_histogram,
)


def _fixture(n_windows: int = 4, window: int = 16) -> tuple:
    frames = np.arange(n_windows * window, dtype=np.float32)
    features = np.repeat(frames[:, None], 2, axis=1)
    features = features.reshape(n_windows, window, 2)
    frame_labels = np.repeat(frames[:, None], 1, axis=1).astype(np.int64)
    frame_labels = frame_labels.reshape(n_windows, window)
    frame_bass = frame_labels.copy()
    offsets = [(0, n_windows, "track")]
    segment_index = build_segment_index(offsets, n_windows)
    return features, frame_labels, frame_bass, offsets, segment_index


class TestContextGeometry:
    def test_centred_context(self):
        features, labels, bass, offsets, segment = _fixture()
        out = context_for_window(features, labels, bass, offsets, segment,
                                 window_index=1, context_frames=32)
        assert out["features"].shape == (32, 2)
        assert out["features"][0, 0] == 8.0
        assert out["center_index"] == 16
        assert out["frame_labels"][16] == 24.0

    def test_clamped_at_start(self):
        features, labels, bass, offsets, segment = _fixture()
        out = context_for_window(features, labels, bass, offsets, segment,
                                 window_index=0, context_frames=32)
        assert out["features"][0, 0] == 0.0
        assert out["center_index"] == 8

    def test_clamped_at_end(self):
        features, labels, bass, offsets, segment = _fixture()
        out = context_for_window(features, labels, bass, offsets, segment,
                                 window_index=3, context_frames=32)
        assert out["features"][-1, 0] == 63.0
        assert out["center_index"] == 24

    def test_short_track_is_padded_and_masked(self):
        features, labels, bass, offsets, segment = _fixture(n_windows=1)
        out = context_for_window(features, labels, bass, offsets, segment,
                                 window_index=0, context_frames=32)
        assert out["features"].shape == (32, 2)
        assert out["valid"][:16].all() and not out["valid"][16:].any()
        assert out["frame_labels"][16] == N_IDX_170
        assert out["frame_bass"][16] == BASS_X_IDX

    def test_second_track_uses_track_offset(self):
        features, labels, bass, _, _ = _fixture()
        features_b = features + 1000.0
        labels_b = labels + 1000
        bass_b = bass + 1000
        all_features = np.concatenate([features, features_b], axis=0)
        all_labels = np.concatenate([labels, labels_b], axis=0)
        all_bass = np.concatenate([bass, bass_b], axis=0)
        offsets = [(0, 4, "a"), (4, 4, "b")]
        segment = build_segment_index(offsets, 8)
        out = context_for_window(all_features, all_labels, all_bass, offsets,
                                 segment, window_index=5, context_frames=32)
        assert out["features"][0, 0] == 1008.0
        assert out["frame_labels"][16] == 1024
        assert out["track_id"] == "b"

    def test_batch_shape_and_centres(self):
        features, labels, bass, offsets, segment = _fixture()
        batch = context_batch(features, labels, bass, offsets, segment,
                             np.array([0, 1, 2]), context_frames=32)
        assert batch["features"].shape == (3, 32, 2)
        assert batch["center_index"].tolist() == [8, 16, 16]
        assert batch["valid"].shape == (3, 32)


class TestStructuredHelpers:
    def test_pitch_table(self):
        row = PITCH_TARGET_TABLE[CHORD_TO_IDX_170["C:maj"]]
        assert row[0] == 1 and row[4] == 1 and row[7] == 1
        assert row.sum() == 3
        assert PITCH_TARGET_TABLE[N_IDX_170].sum() == 0

    def test_pitch_targets_shape(self):
        chords = np.array([[CHORD_TO_IDX_170["C:maj"], N_IDX_170]])
        targets = pitch_targets_from_chords(chords)
        assert targets.shape == (1, 2, 12)
        assert targets[0, 0].sum() == 3

    def test_root_quality(self):
        chords = np.array([CHORD_TO_IDX_170["C:maj"], N_IDX_170])
        roots, qualities = root_quality_from_chords(chords)
        assert roots.tolist() == [0, 12]
        assert qualities.tolist() == [0, 14]

    def test_inversion(self):
        chord = np.array([CHORD_TO_IDX_170["C:maj"]])
        bass = np.array([4])
        assert inversion_from_chord_bass(chord, bass).tolist() == [1]

    def test_fuse_prefers_consistent_class(self):
        target = CHORD_TO_IDX_170["C:maj"]
        chord = np.full((1, 170), 1e-6, dtype=np.float32)
        chord[0, target] = 0.4
        chord[0, CHORD_TO_IDX_170["C:min"]] = 0.35
        root = np.full((1, 13), 1e-6, dtype=np.float32)
        root[0, 0] = 0.9
        quality = np.full((1, 15), 1e-6, dtype=np.float32)
        quality[0, 0] = 0.9
        assert structured_decode(chord, root, quality, mode="fuse")[0] == target

    def test_hybrid_uses_pitch(self):
        target = CHORD_TO_IDX_170["C:maj"]
        chord = np.full((1, 170), 1e-6, dtype=np.float32)
        chord[0, target] = 0.1
        chord[0, CHORD_TO_IDX_170["C:min"]] = 0.2
        root = np.full((1, 13), 1e-6, dtype=np.float32)
        root[0, 0] = 0.9
        quality = np.full((1, 15), 1e-6, dtype=np.float32)
        quality[0, 0] = 0.9
        pitch = np.zeros((1, 12), dtype=np.float32)
        pitch[0, [0, 4, 7]] = 0.9
        assert structured_decode(chord, root, quality, pitch, mode="hybrid")[0] == target


class TestSupportMetrics:
    def test_min_support_macro(self):
        y_true = np.array([0] * 10 + [1] * 3)
        y_pred = np.array([0] * 10 + [1] * 3)
        assert macro_f1_min_support(y_true, y_pred, 5) == 1.0
        assert macro_f1_min_support(y_true, y_pred, 10) == 1.0
        assert macro_f1_min_support(y_true, y_pred, 20) == 0.0

    def test_support_histogram(self):
        y_true = np.array([0] * 20 + [1] * 10 + [2] * 4 + [3])
        hist = support_histogram(y_true)
        assert hist["20+"] == 1
        assert hist["10-19"] == 1
        assert hist["2-4"] == 1
        assert hist["1"] == 1
