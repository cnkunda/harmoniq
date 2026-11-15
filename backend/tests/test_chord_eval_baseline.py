"""Tests for the Phase 0 baseline evaluation harness (Chord 170 program)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR.parent))

from scripts.eval_chord_baseline import (  # noqa: E402
    chord_metrics_25,
    gate_impact,
    map_277_to_mirex25,
)
from app.chord_vocab import (  # noqa: E402
    CHORD_TO_IDX,
    CHORD_VOCAB,
    MIREX_TO_IDX,
    MIREX_VOCAB,
    NUM_CLASSES,
    NUM_CLASSES_MIREX,
    mirex_label,
)


class TestMirexMapping:
    def test_mapping_shape(self):
        idx = np.arange(NUM_CLASSES, dtype=np.int64)
        mapped = map_277_to_mirex25(idx)
        assert mapped.shape == (NUM_CLASSES,)
        assert mapped.min() >= 0
        assert mapped.max() < NUM_CLASSES_MIREX

    def test_major_and_minor_identity(self):
        assert mirex_label(MIREX_TO_IDX["C:maj"]) == MIREX_TO_IDX["C:maj"]
        assert mirex_label(MIREX_TO_IDX["G:min"]) == MIREX_TO_IDX["G:min"]

    def test_n_maps_to_n(self):
        assert mirex_label(NUM_CLASSES - 1) == NUM_CLASSES_MIREX - 1

    def test_dominant_maps_to_major(self):
        assert mirex_label(CHORD_TO_IDX["C:7"]) == MIREX_TO_IDX["C:maj"]
        assert mirex_label(CHORD_TO_IDX["A:9"]) == MIREX_TO_IDX["A:maj"]

    def test_minor7_maps_to_minor(self):
        assert mirex_label(CHORD_TO_IDX["E:min7"]) == MIREX_TO_IDX["E:min"]

    def test_chord_vocab_consistency(self):
        # MIREX vocab must be a strict subset of the 277-class vocabulary
        for label in MIREX_VOCAB:
            assert label in CHORD_VOCAB


class TestChordMetrics25:
    def test_perfect_predictions(self):
        y = np.array([0, 1, 24, 13, 24])
        m = chord_metrics_25(y, y)
        assert m["exact_accuracy"] == 1.0
        assert m["root_accuracy"] == 1.0
        assert m["macro_f1"] == 1.0
        assert m["n_windows"] == 5

    def test_root_accuracy_merges_quality(self):
        # C:maj (0) predicted as C:maj7's MIREX image — use maj→min confusion:
        # truth C:maj (0), prediction C:min (12) → root match, quality mismatch
        y_true = np.array([0])
        y_pred = np.array([12])
        m = chord_metrics_25(y_true, y_pred)
        assert m["exact_accuracy"] == 0.0
        assert m["root_accuracy"] == 1.0

    def test_n_mismatch_counts_against_root(self):
        y_true = np.array([0])
        y_pred = np.array([24])
        m = chord_metrics_25(y_true, y_pred)
        assert m["root_accuracy"] == 0.0

    def test_macro_f1_zero_overlap(self):
        y_true = np.array([0, 0])
        y_pred = np.array([12, 12])
        m = chord_metrics_25(y_true, y_pred)
        assert m["macro_f1"] == 0.0

    def test_top3_accuracy(self):
        y_true = np.array([0, 13])
        probs = np.full((2, 25), 0.01)
        probs[0, 0] = 0.5
        probs[0, 3] = 0.2
        probs[0, 7] = 0.1
        probs[1, 9] = 0.5
        probs[1, 5] = 0.2
        probs[1, 11] = 0.1
        m = chord_metrics_25(y_true, np.array([0, 9]), probs)
        assert m["top3_accuracy"] == 0.5

    def test_top3_miss(self):
        y_true = np.array([13])
        probs = np.zeros((1, 25), dtype=np.float64)
        probs[0, 0] = 0.5
        probs[0, 3] = 0.2
        probs[0, 7] = 0.1
        m = chord_metrics_25(y_true, np.array([0]), probs)
        assert m["top3_accuracy"] == 0.0

    def test_empty_input(self):
        m = chord_metrics_25(np.array([], dtype=np.int64), np.array([], dtype=np.int64))
        assert m["n_windows"] == 0
        assert m["exact_accuracy"] == 0.0


class TestGateImpact:
    def test_gate_regresses_correct_predictions(self):
        y_true = np.array([0, 5, 12])
        y_head = np.array([0, 5, 12])
        y_gated = np.array([24, 5, 24])
        impact = gate_impact(y_true, y_head, y_gated)
        assert impact["n_forced_changed"] == 2
        assert impact["correct_to_wrong"] == 2
        assert impact["wrong_to_correct"] == 0

    def test_gate_can_help(self):
        y_true = np.array([24, 5])
        y_head = np.array([0, 5])
        y_gated = np.array([24, 5])
        impact = gate_impact(y_true, y_head, y_gated)
        assert impact["n_forced_changed"] == 1
        assert impact["correct_to_wrong"] == 0
        assert impact["wrong_to_correct"] == 1


class TestLoadWindows:
    def test_load_windows_split_filter(self, tmp_path):
        npz_a = tmp_path / "a.npz"
        npz_b = tmp_path / "b.npz"
        np.savez(
            npz_a,
            features=np.zeros((2, 128, 144), dtype=np.float32),
            labels=np.array([0, 5], dtype=np.int32),
            track_id="track_a",
            player_id="05",
            split="test",
            loss_weight=np.array(1.0),
        )
        np.savez(
            npz_b,
            features=np.zeros((1, 128, 144), dtype=np.float32),
            labels=np.array([24], dtype=np.int32),
            track_id="track_b",
            player_id="04",
            split="val",
            loss_weight=np.array(1.0),
        )
        from scripts.eval_chord_baseline import load_windows

        result = load_windows(tmp_path, "test")
        assert result["n_tracks"] == 1
        assert result["features"].shape == (2, 128, 144)
        assert result["track_ids"] == ["track_a", "track_a"]

        val = load_windows(tmp_path, "val")
        assert val["n_tracks"] == 1
        assert val["features"].shape == (1, 128, 144)

    def test_load_windows_empty(self, tmp_path):
        from scripts.eval_chord_baseline import load_windows

        result = load_windows(tmp_path, "test")
        assert result["n_tracks"] == 0
        assert len(result["labels277"]) == 0


@pytest.mark.parametrize("quality,expected", [("maj", "maj"), ("min", "min"), ("7", "maj")])
def test_mirex_quality_images(quality, expected):
    assert mirex_label(CHORD_TO_IDX[f"D:{quality}"]) == MIREX_TO_IDX[f"D:{expected}"]
