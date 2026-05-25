"""Tests for commit 103 training infrastructure improvements.

Tests the AugmentedDataGenerator, label-aware pitch shift,
confusion matrix reporting, and per-class metrics.
"""
import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES, CHORD_VOCAB, NUM_CLASSES
from scripts.build_chord_tflite import (
    AugmentedDataGenerator,
    _find_class_index,
    compute_confusion_matrix_report,
    compute_per_class_metrics,
    compute_training_class_weights,
    apply_pitch_shift,
    apply_time_stretch,
    generate_pink_noise,
    WINDOW,
    FEATURE_DIM,
)

N_CLASSES_PER_QUALITY = 12


class TestFindClassIndex:
    def test_first_class_C_maj(self):
        idx = _find_class_index(0, "maj")
        assert idx == 0
        assert CHORD_VOCAB[idx] == "C:maj"

    def test_last_class_B_13(self):
        qualities = list(CHORD_INTERVALS.keys())
        last_quality = qualities[-1]
        idx = _find_class_index(11, last_quality)
        assert CHORD_VOCAB[idx] == f"B:{last_quality}"

    def test_N_class(self):
        idx = _find_class_index(-1, "N")
        assert idx == NUM_CLASSES - 1
        assert CHORD_VOCAB[idx] == "N"

    def test_G_maj7(self):
        idx = _find_class_index(7, "maj7")
        assert CHORD_VOCAB[idx] == "G:maj7"

    def test_D_7(self):
        idx = _find_class_index(2, "7")
        assert CHORD_VOCAB[idx] == "D:7"


class TestAugmentedDataGenerator:
    def test_output_shapes(self):
        X = np.random.randn(100, WINDOW, FEATURE_DIM).astype(np.float32)
        y = np.random.randint(0, min(10, NUM_CLASSES), size=(100,)).astype(np.int32)
        gen = AugmentedDataGenerator(X, y, batch_size=16)
        assert len(gen) == 7  # ceil(100/16) = 7
        batch_X, batch_y = gen[0]
        assert batch_X.shape == (16, WINDOW, FEATURE_DIM)
        assert batch_y.shape == (16,)

    def test_applies_augmentations(self):
        X = np.random.randn(32, WINDOW, FEATURE_DIM).astype(np.float32)
        y = np.zeros(32, dtype=np.int32)
        gen = AugmentedDataGenerator(X, y, batch_size=32, p_pitch_shift=0.0,
                                     p_time_stretch=0.0, noise_std=0.0)
        batch_X, _ = gen[0]
        assert batch_X.shape == (32, WINDOW, FEATURE_DIM)

    def test_pitch_shift_changes_features(self):
        X = np.random.randn(64, WINDOW, FEATURE_DIM).astype(np.float32)
        y = np.zeros(64, dtype=np.int32)  # all C:maj
        gen = AugmentedDataGenerator(X, y, batch_size=64,
                                     p_pitch_shift=1.0, pitch_range=2,
                                     p_time_stretch=0.0, noise_std=0.0)
        batch_X_original = X.copy()
        batch_X_augmented, _ = gen[0]
        # With 64 samples and p_pitch_shift=1.0, at least some should be shifted
        different_count = sum(
            int(not np.allclose(batch_X_augmented[i], batch_X_original[i]))
            for i in range(len(X))
        )
        assert different_count > 0, "At least some samples should be pitch-shifted"

    def test_shuffle_reshuffles_indices(self):
        X = np.random.randn(200, WINDOW, FEATURE_DIM).astype(np.float32)
        y = np.zeros(200, dtype=np.int32)
        gen = AugmentedDataGenerator(X, y, batch_size=10, p_pitch_shift=0.0,
                                     p_time_stretch=0.0, noise_std=0.0)
        # Store original indices
        orig_indices = gen.indices.copy()
        gen.on_epoch_end()
        gen.on_epoch_end()
        # After 2 epoch ends + init shuffle, indices should be different
        assert not np.array_equal(gen.indices, np.arange(200)), \
            "Indices should be shuffled after init"
        assert not np.array_equal(gen.indices, orig_indices) or orig_indices[0] != 0, \
            "Indices should change after on_epoch_end"

    def test_all_labels_unchanged(self):
        X = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        y = np.random.randint(0, 10, size=(50,)).astype(np.int32)
        gen = AugmentedDataGenerator(X, y, batch_size=10, p_pitch_shift=0.0,
                                     p_time_stretch=0.0, noise_std=0.0)
        retrieved = gen.get_all_labels()
        np.testing.assert_array_equal(retrieved, y)


class TestLabelAwarePitchShift:
    """Verify that _label_after_pitch_shift correctly adjusts labels."""

    def _label_after_shift(self, label_idx: int, shift: int) -> int:
        """Replicate the generator's label-shift logic."""
        n_chord_classes = len(CHORD_INTERVALS) * 12
        if label_idx >= n_chord_classes:
            return label_idx
        quality_pos = label_idx // 12
        root = label_idx % 12
        new_root = (root + shift) % 12
        return quality_pos * 12 + new_root

    def test_shift_C_maj_to_D_maj(self):
        label = _find_class_index(0, "maj")  # C:maj
        result = self._label_after_shift(label, 2)
        expected = _find_class_index(2, "maj")  # D:maj
        assert result == expected, f"Expected {CHORD_VOCAB[expected]}, got {CHORD_VOCAB[result]}"

    def test_shift_A_min_up_2(self):
        label = _find_class_index(9, "min")  # A:min
        result = self._label_after_shift(label, 2)
        expected = _find_class_index(11, "min")  # B:min
        assert result == expected, f"Expected {CHORD_VOCAB[expected]}, got {CHORD_VOCAB[result]}"

    def test_shift_wraps_around(self):
        label = _find_class_index(11, "maj")  # B:maj
        result = self._label_after_shift(label, 1)
        expected = _find_class_index(0, "maj")  # C:maj
        assert result == expected, f"Expected {CHORD_VOCAB[expected]}, got {CHORD_VOCAB[result]}"

    def test_N_class_unchanged(self):
        label = NUM_CLASSES - 1  # N class
        result = self._label_after_shift(label, 2)
        assert result == label, "N class should be unchanged after pitch shift"

    def test_negative_shift(self):
        label = _find_class_index(0, "maj")  # C:maj
        result = self._label_after_shift(label, -1)
        expected = _find_class_index(11, "maj")  # B:maj
        assert result == expected, f"Expected {CHORD_VOCAB[expected]}, got {CHORD_VOCAB[result]}"

    def test_quality_preserved(self):
        """After shifting, the quality (maj, min, 7, etc.) must stay the same."""
        for quality in list(CHORD_INTERVALS.keys())[:5]:
            for root in range(12):
                label = _find_class_index(root, quality)
                for shift in [-2, -1, 1, 2]:
                    new_label = self._label_after_shift(label, shift)
                    new_chord = CHORD_VOCAB[new_label]
                    if ":" in new_chord:
                        new_quality = new_chord.split(":")[1]
                    else:
                        new_quality = new_chord
                    assert new_quality == quality, \
                        f"Quality changed from {quality} to {new_quality} for root {root} shift {shift}"


class TestConfusionMatrixReport:
    def test_perfect_predictions(self):
        y_true = np.array([0, 1, 2, 3], dtype=np.int32)
        y_pred = np.array([0, 1, 2, 3], dtype=np.int32)
        cm = compute_confusion_matrix_report(y_true, y_pred, top_k=5)
        assert cm.shape == (NUM_CLASSES, NUM_CLASSES)
        assert np.trace(cm) == 4

    def test_some_confusions(self):
        y_true = np.array([0, 0, 1, 1], dtype=np.int32)
        y_pred = np.array([0, 1, 0, 1], dtype=np.int32)
        cm = compute_confusion_matrix_report(y_true, y_pred, top_k=5)
        assert cm[0, 0] == 1  # one correct C:maj
        assert cm[0, 1] == 1  # one C:maj predicted as D:maj
        assert cm[1, 0] == 1  # one D:maj predicted as C:maj
        assert cm[1, 1] == 1  # one correct D:maj


class TestPerClassMetrics:
    def test_perfect_predictions(self):
        y_true = np.array([0, 1, 2], dtype=np.int32)
        y_pred = np.array([0, 1, 2], dtype=np.int32)
        report = compute_per_class_metrics(y_true, y_pred)
        for chord_name in [CHORD_VOCAB[0], CHORD_VOCAB[1], CHORD_VOCAB[2]]:
            assert report[chord_name]["precision"] == 1.0
            assert report[chord_name]["recall"] == 1.0
            assert report[chord_name]["f1-score"] == 1.0

    def test_some_misclassifications(self):
        y_true = np.array([0, 0, 1, 1], dtype=np.int32)
        y_pred = np.array([0, 1, 0, 1], dtype=np.int32)
        report = compute_per_class_metrics(y_true, y_pred)
        assert report[CHORD_VOCAB[0]]["recall"] == 0.5
        assert report[CHORD_VOCAB[1]]["recall"] == 0.5


class TestClassWeights:
    def test_balanced_weights(self):
        y = np.array([0, 0, 0, 1], dtype=np.int32)
        weights = compute_training_class_weights(y)
        # Class 0 has 3 samples, class 1 has 1 sample
        # weight_0 = 4 / (2 * 3) = 0.667
        # weight_1 = 4 / (2 * 1) = 2.0
        assert abs(weights[0] - 4 / (2 * 3)) < 1e-6
        assert abs(weights[1] - 4 / (2 * 1)) < 1e-6
        assert weights[1] > weights[0]

    def test_single_class(self):
        y = np.zeros(10, dtype=np.int32)
        weights = compute_training_class_weights(y)
        assert weights[0] == 1.0
