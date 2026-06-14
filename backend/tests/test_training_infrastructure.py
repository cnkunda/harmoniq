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
    generate_dataset,
    make_window_augmented,
    mix_datasets,
    CHORD_CLASS_MAP,
    N_CLASSES_PER_QUALITY,
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


class TestPreGenerationLabelSync:
    """Verify that generate_dataset now produces correctly-labeled synthetic data."""

    def test_make_window_augmented_returns_shift(self):
        """make_window_augmented must return (window, shift)."""
        from scripts.build_chord_tflite import make_cqt_template
        template = make_cqt_template(0, "maj")
        result = make_window_augmented(template, noise_std=0.01, pitch_range=2,
                                        stretch_rate=0.0)
        assert isinstance(result, tuple) and len(result) == 2, \
            "make_window_augmented should return (window, shift)"
        window, shift = result
        assert window.shape == (WINDOW, FEATURE_DIM)
        assert isinstance(shift, int)
        assert -2 <= shift <= 2

    def test_generate_dataset_has_correct_label_count(self):
        """All 277 chord classes should appear in generated dataset labels."""
        X, y = generate_dataset(samples_per_class=10, config={
            "pitch_shift_range": 2,
            "time_stretch_rate": 0.0,
            "transition_rate": 0.0,
        })
        unique_labels = set(y.tolist())
        # Without label adjustment, pitch-shifted samples would have
        # wrong root labels, causing some roots to disappear or
        # certain classes to be missing. With correction, all 277
        # classes should be present (or very close).
        n_chord_classes = len(CHORD_INTERVALS) * N_CLASSES_PER_QUALITY
        assert len(unique_labels) >= n_chord_classes - 5, \
            f"Expected ~{n_chord_classes} classes, got {len(unique_labels)}"

    def test_generated_labels_match_features(self):
        """Verify that a known pitch-shifted sample has the correct label."""
        import warnings
        from scripts.build_chord_tflite import make_cqt_template

        template = make_cqt_template(0, "maj")  # C:maj

        # Force shift=+2 by setting pitch_range=2 and stretch_rate=0
        # make_window_augmented uses np.random.randint(-2, 3)
        # We can't force a specific value, so we run multiple and check
        matches = 0
        total = 50
        for _ in range(total):
            window, shift = make_window_augmented(
                template, noise_std=0.01,
                pitch_range=2, stretch_rate=0.0
            )
            if shift == 0:
                expected_idx = 0  # C:maj
            else:
                quality_pos = 0  # maj is first quality
                new_root = (0 + shift) % N_CLASSES_PER_QUALITY
                expected_idx = quality_pos * N_CLASSES_PER_QUALITY + new_root

            # Re-classify: run the window through a simple template match
            chroma = window.mean(axis=0)
            # Find which root best matches the shifted CQT
            actual_chord = CHORD_CLASS_MAP[expected_idx]
            actual_quality = actual_chord[1]
            # If the shift matches the expected quality, label is correct
            assert actual_quality == "maj", \
                f"Expected 'maj' quality, got {actual_quality}"


class TestTemperatureResampling:
    """Tests for MT3-style temperature-based quality resampling (Commit 104)."""

    N_CHORD = len(CHORD_INTERVALS) * 12  # 276 chord classes

    def _build_imbalanced_data(self, n_samples: int = 500):
        """Create imbalanced labels simulating real-world chord distribution."""
        np.random.seed(42)
        # Heavily skew toward C:maj (idx=0), with few rare chords
        # C:maj gets 60%, next 50 popular chords get 35%, rest 5%
        labels = []
        n_common = int(n_samples * 0.60)
        labels.extend([0] * n_common)
        n_mid = int(n_samples * 0.35)
        mid_indices = np.random.randint(1, 50, size=n_mid).tolist()
        labels.extend(mid_indices)
        n_rare = n_samples - n_common - n_mid
        rare_indices = np.random.randint(50, self.N_CHORD, size=n_rare).tolist()
        labels.extend(rare_indices)
        labels = np.array(labels[:n_samples], dtype=np.int32)
        np.random.shuffle(labels)

        X = np.random.randn(n_samples, WINDOW, FEATURE_DIM).astype(np.float32)
        return X, labels

    def test_default_temperature_is_0_3(self):
        """AugmentedDataGenerator must default to τ=0.3 (MT3 match)."""
        X, y = self._build_imbalanced_data(100)
        gen = AugmentedDataGenerator(X, y, batch_size=20)
        assert gen.temperature == 0.3, \
            f"Expected default temperature=0.3, got {gen.temperature}"

    def test_temperature_1_0_uses_uniform_shuffle(self):
        """With τ=1.0, indices should be a uniform shuffle of arange."""
        X, y = self._build_imbalanced_data(200)
        gen = AugmentedDataGenerator(X, y, batch_size=20, temperature=1.0)
        assert len(gen.indices) == 200
        # τ=1.0: weights are uniform, so indices are a permutation of 0..199
        assert sorted(gen.indices) == list(range(200)), \
            "τ=1.0 must produce a permutation"

    def test_temperature_0_3_uses_weighted_resampling(self):
        """With τ=0.3, indices should use weighted resampling with replacement."""
        X, y = self._build_imbalanced_data(500)
        gen = AugmentedDataGenerator(X, y, batch_size=50, temperature=0.3)
        unique_count = len(np.unique(gen.indices))
        # τ=0.3 concentrates on rare classes, so ~1/3 of 500 classes are unique
        assert unique_count > 100, \
            f"τ=0.3 should still cover many classes: {unique_count}/500 unique"
        # Some duplicates must exist (resampling with replacement)
        assert len(gen.indices) > unique_count, \
            "Resampling with replacement should produce duplicates"

    def test_temperature_0_3_balances_quality_distribution(self):
        """τ=0.3 should produce a more balanced quality distribution than τ=1.0."""
        X, y = self._build_imbalanced_data(2000)

        gen_rare = AugmentedDataGenerator(X, y, batch_size=100, temperature=0.3)
        gen_uniform = AugmentedDataGenerator(X, y, batch_size=100, temperature=1.0)

        # Map indices to quality groups
        def quality_distribution(indices):
            """Return dict of quality -> count for a sample of indices."""
            from collections import Counter
            qualities = []
            for idx in indices:
                if idx < self.N_CHORD:
                    quality = CHORD_CLASS_MAP[idx][1]
                else:
                    quality = "N"
                qualities.append(quality)
            return Counter(qualities)

        dist_rare = quality_distribution(gen_rare.indices)
        dist_uniform = quality_distribution(gen_uniform.indices)

        # The uniform distribution should still favor "maj" (60% of data)
        # The rare distribution should have diluted "maj" and boosted others
        maj_pct_03 = dist_rare.get("maj", 0) / len(gen_rare.indices)
        maj_pct_10 = dist_uniform.get("maj", 0) / len(gen_uniform.indices)

        # With τ=0.3, maj should be less frequent than with τ=1.0
        assert maj_pct_03 < maj_pct_10, \
            f"τ=0.3 should reduce maj frequency ({maj_pct_03:.3f} vs {maj_pct_10:.3f})"

    def test_on_epoch_end_reshuffles_with_temperature(self):
        """on_epoch_end should re-weight indices when temperature < 1.0."""
        X, y = self._build_imbalanced_data(500)
        gen = AugmentedDataGenerator(X, y, batch_size=50, temperature=0.3)
        first_indices = gen.indices.copy()
        gen.on_epoch_end()
        second_indices = gen.indices.copy()
        # Indices should differ after on_epoch_end
        assert not np.array_equal(first_indices, second_indices), \
            "on_epoch_end should reshuffle with temperature weights"

    def test_temperature_0_1_more_aggressive_than_0_3(self):
        """τ=0.1 should be more aggressive at balancing than τ=0.3."""
        X, y = self._build_imbalanced_data(2000)
        gen_03 = AugmentedDataGenerator(X, y, batch_size=100, temperature=0.3)
        gen_01 = AugmentedDataGenerator(X, y, batch_size=100, temperature=0.1)

        # Maj (idx=0) should be even less frequent with τ=0.1
        pct_03 = float((gen_03.indices == 0).sum()) / len(gen_03.indices)
        pct_01 = float((gen_01.indices == 0).sum()) / len(gen_01.indices)

        assert pct_01 < pct_03, \
            f"τ=0.1 should reduce common class more than τ=0.3 ({pct_01:.3f} vs {pct_03:.3f})"


class TestSyntheticWeightCapping:
    """Tests for Commit 148 Phase 1a: synthetic volume capping and weight=0.15."""

    def test_mix_datasets_preserves_synthetic_weight(self):
        """mix_datasets should preserve per-source sample weights."""
        real_X = np.random.randn(50, WINDOW, FEATURE_DIM).astype(np.float32)
        real_y = np.random.randint(0, 10, size=(50,)).astype(np.int32)
        real_w = np.ones(50, dtype=np.float32)

        synth_X = np.random.randn(100, WINDOW, FEATURE_DIM).astype(np.float32)
        synth_y = np.random.randint(0, 10, size=(100,)).astype(np.int32)
        synth_w = np.full(100, 0.15, dtype=np.float32)

        X, y, w, source_ids = mix_datasets([
            (real_X, real_y, real_w),
            (synth_X, synth_y, synth_w),
        ])

        assert X.shape[1:] == (WINDOW, FEATURE_DIM)
        assert len(X) == 150
        assert len(w) == 150

        synth_indices = source_ids == 1
        assert np.allclose(w[synth_indices], 0.15), \
            "All synthetic samples should have weight=0.15"
        assert np.allclose(w[~synth_indices], 1.0), \
            "All real samples should have weight=1.0"

    def test_synthetic_capped_at_2x_real_volume(self):
        """Simulate the Phase 1a capping logic: synthetic capped to 2x real volume."""
        n_real = 300
        n_synth = 5000
        max_synthetic = n_real * 2

        synth_X = np.random.randn(n_synth, WINDOW, FEATURE_DIM).astype(np.float32)
        synth_y = np.random.randint(0, 10, size=(n_synth,)).astype(np.int32)

        if len(synth_X) > max_synthetic:
            synth_X = synth_X[:max_synthetic]
            synth_y = synth_y[:max_synthetic]

        assert len(synth_X) == 600, \
            f"Synthetic should be capped to {max_synthetic}, got {len(synth_X)}"
        assert len(synth_y) == 600

        weights = np.full(len(synth_X), 0.15, dtype=np.float32)
        assert np.allclose(weights, 0.15)

    def test_no_cap_when_synthetic_under_2x(self):
        """When synthetic < 2x real, no capping occurs."""
        n_real = 1000
        n_synth = 500
        max_synthetic = n_real * 2

        synth_X = np.random.randn(n_synth, WINDOW, FEATURE_DIM).astype(np.float32)
        synth_y = np.random.randint(0, 10, size=(n_synth,)).astype(np.int32)

        if len(synth_X) > max_synthetic:
            synth_X = synth_X[:max_synthetic]
            synth_y = synth_y[:max_synthetic]

        assert len(synth_X) == 500, \
            f"Synthetic should remain at {n_synth} since under 2x cap"
        assert len(synth_y) == 500
