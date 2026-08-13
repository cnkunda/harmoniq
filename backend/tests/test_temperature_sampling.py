"""Tests for temperature sampling (Commit 104) and per-class recall metrics."""
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

from build_chord_tflite import (
    CHORD_INTERVALS,
    CHORD_CLASS_MAP,
    CHORD_VOCAB,
    NUM_CLASSES,
    RARE_CHORD_TYPES,
    compute_temperature_weights,
    compute_samples_per_quality,
    compute_per_class_recall,
    compute_rare_chord_metrics,
)


class TestTemperatureWeights:
    """Test MT3 temperature sampling weight computation."""

    def test_uniform_at_temperature_1(self):
        """At T=1.0, weights should be proportional to frequency (no rebalancing)."""
        weights = compute_temperature_weights(temperature=1.0)
        # All qualities with count > 0 should have weight proportional to freq
        assert weights["maj"] > weights["min"]  # maj (40%) > min (12%)
        assert weights["7"] > weights["dim7"]    # 7 (24%) > dim7 (3.4%)

    def test_uniform_at_temperature_0(self):
        """At T=0.0, all qualities should have equal weight."""
        weights = compute_temperature_weights(temperature=0.0)
        for q in CHORD_INTERVALS:
            assert weights[q] == pytest.approx(1.0, abs=1e-6), f"Quality {q} not uniform at T=0"

    def test_mt3_default_temperature(self):
        """At T=0.3, rare types should be boosted relative to common types."""
        weights = compute_temperature_weights(temperature=0.3)
        # Rare types should get higher weight than their raw frequency suggests
        # "11" has count 14 (0.04%), "maj" has 14336 (40.25%)
        # At T=0.3: weight_11 = (14/35613)^0.3 ≈ 0.04^0.3 ≈ 0.32
        #           weight_maj = (14336/35613)^0.3 ≈ 0.40^0.3 ≈ 0.74
        # Ratio without T: 0.04/0.40 = 0.10
        # Ratio with T: 0.32/0.74 = 0.43 → rare type boosted 4x
        assert weights["11"] > 0
        assert weights["maj"] > 0
        # Verify rebalancing: ratio should be higher than raw frequency ratio
        raw_ratio = (14 / 35613) / (14336 / 35613)
        temp_ratio = weights["11"] / weights["maj"]
        assert temp_ratio > raw_ratio, "Temperature sampling should boost rare types"

    def test_all_qualities_have_weights(self):
        """Every quality in CHORD_INTERVALS should have a weight."""
        weights = compute_temperature_weights(temperature=0.3)
        for quality in CHORD_INTERVALS:
            assert quality in weights, f"Missing weight for quality: {quality}"
            assert weights[quality] > 0, f"Zero weight for quality: {quality}"

    def test_zero_count_qualities_get_floor_weight(self):
        """Qualities with count=0 should still get non-zero weight (floor at 1)."""
        weights = compute_temperature_weights(temperature=0.3)
        # "alt7" and "7sus4" have count=0 in distribution
        assert weights.get("alt7", 0) > 0
        assert weights.get("7sus4", 0) > 0


class TestSamplesPerQuality:
    """Test per-quality sample count computation."""

    def test_output_keys_match_qualities(self):
        samples = compute_samples_per_quality(base_samples_per_class=200, temperature=0.3)
        for quality in CHORD_INTERVALS:
            assert quality in samples

    def test_clamped_range(self):
        """Samples should be clamped between 20 and 800."""
        samples = compute_samples_per_quality(base_samples_per_class=200, temperature=0.3)
        for quality, count in samples.items():
            assert 20 <= count <= 800, f"Quality {quality}: {count} out of range"

    def test_rare_types_get_more_samples(self):
        """Temperature sampling flattens the common/rare sample ratio.

        MT3 sampling uses (n_i/Σn_j)^T; T<1 compresses the weight spread,
        so the maj:11 ratio (≈1024× proportional) shrinks toward 1 as T
        drops, and rare types get far more samples than their natural share.
        """
        s03 = compute_samples_per_quality(base_samples_per_class=200, temperature=0.3)
        # "11" (count=14/35613) must exceed its proportional share (≈0.08)
        assert s03["11"] > 0.08 * 200, \
            f"Rare type '11' ({s03['11']}) should be oversampled vs proportional"
        # Common type must still dominate absolute counts at T=0.3
        assert s03["maj"] > s03["11"], \
            f"'maj' ({s03['maj']}) should still outweigh '11' ({s03['11']}) at T=0.3"
        # Lower T flattens the ratio further
        ratio_10 = compute_samples_per_quality(200, temperature=1.0)
        ratio_01 = compute_samples_per_quality(200, temperature=0.1)
        assert (ratio_10["maj"] / ratio_10["11"]) > (s03["maj"] / s03["11"]) > (
            ratio_01["maj"] / ratio_01["11"]
        ), "maj:11 ratio must shrink monotonically as T decreases"

    def test_temperature_zero_gives_uniform(self):
        """At T=0, all qualities should get approximately equal samples."""
        samples = compute_samples_per_quality(base_samples_per_class=200, temperature=0.0)
        values = list(samples.values())
        # All should be approximately 200 (the base)
        for v in values:
            assert v == pytest.approx(200, rel=0.1), f"Expected ~200 at T=0, got {v}"

    def test_total_dataset_size_reasonable(self):
        """Total dataset size should be in a reasonable range."""
        samples = compute_samples_per_quality(base_samples_per_class=200, temperature=0.3)
        total_per_root = sum(samples.values())
        total_all_roots = total_per_root * 12  # 12 roots per quality
        # Should be roughly 277 classes × 200 samples = 55,400 (within 3x)
        assert 10000 < total_all_roots < 200000, f"Total dataset size {total_all_roots} seems unreasonable"


class TestPerClassRecall:
    """Test per-chord-type recall computation."""

    def test_perfect_predictions(self):
        """Perfect predictions should give recall=1.0 for all types."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        result = compute_per_class_recall(y_true, y_pred)
        for quality, metrics in result.items():
            assert metrics["recall"] == 1.0, f"Quality {quality}: expected recall=1.0, got {metrics['recall']}"

    def test_all_wrong_predictions(self):
        """All-wrong predictions should give recall=0.0 for all types."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.full(n, n - 1, dtype=np.int32)  # All predict last class
        result = compute_per_class_recall(y_true, y_pred)
        for quality, metrics in result.items():
            if metrics["support"] > 0:
                assert metrics["recall"] == 0.0, f"Quality {quality}: expected recall=0.0"

    def test_support_count(self):
        """Support should count the number of true samples per quality."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        result = compute_per_class_recall(y_true, y_pred)
        # Each quality has exactly 12 roots, so support should be 12
        for quality, metrics in result.items():
            if quality != "N":
                assert metrics["support"] == 12, \
                    f"Quality {quality}: expected support=12, got {metrics['support']}"

    def test_top_k_recall(self):
        """Top-k recall should be >= standard recall."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        all_probs = np.eye(n, dtype=np.float32)  # Perfect confidence

        recall_1 = compute_per_class_recall(y_true, y_pred, top_k=1, all_probs=all_probs)
        recall_3 = compute_per_class_recall(y_true, y_pred, top_k=3, all_probs=all_probs)

        for quality in CHORD_INTERVALS:
            if recall_1[quality]["support"] > 0:
                assert recall_3[quality]["recall"] >= recall_1[quality]["recall"], \
                    f"Quality {quality}: top-3 recall should be >= top-1"

    def test_returns_all_qualities(self):
        """Result should contain all chord qualities."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        result = compute_per_class_recall(y_true, y_pred)
        for quality in CHORD_INTERVALS:
            assert quality in result, f"Missing quality: {quality}"


class TestRareChordMetrics:
    """Test rare chord aggregate metrics."""

    def test_perfect_predictions(self):
        """Perfect predictions should give rare_recall=1.0."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        per_class = compute_per_class_recall(y_true, y_pred)
        metrics = compute_rare_chord_metrics(per_class)
        assert metrics["rare_recall"] == 1.0
        assert metrics["common_recall"] == 1.0

    def test_rare_support_counted(self):
        """Rare support should sum all rare chord type supports."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        per_class = compute_per_class_recall(y_true, y_pred)
        metrics = compute_rare_chord_metrics(per_class)

        # Count rare chord types: each has 12 roots
        expected_rare_support = len(RARE_CHORD_TYPES) * 12
        assert metrics["rare_support"] == expected_rare_support

    def test_common_support_counted(self):
        """Common support should sum maj + min supports."""
        n = NUM_CLASSES
        y_true = np.arange(n, dtype=np.int32)
        y_pred = np.arange(n, dtype=np.int32)
        per_class = compute_per_class_recall(y_true, y_pred)
        metrics = compute_rare_chord_metrics(per_class)
        assert metrics["common_support"] == 24  # 12 roots × 2 qualities (maj, min)


class TestTemperatureDataset:
    """Integration test: temperature sampling produces correct dataset shape."""

    def test_dataset_shape_with_temperature(self):
        """Temperature-sampled dataset should have correct dimensions."""
        from build_chord_tflite import generate_dataset

        X, y = generate_dataset(samples_per_class=10, config={"temperature": 0.3})
        assert X.ndim == 3
        assert X.shape[1] == 128  # WINDOW
        assert X.shape[2] == 40   # FEATURE_DIM
        assert len(y) == len(X)
        assert len(X) > 0

    def test_dataset_shape_without_temperature(self):
        """Uniform dataset should have correct dimensions."""
        from build_chord_tflite import generate_dataset

        X, y = generate_dataset(samples_per_class=10)
        assert X.ndim == 3
        assert X.shape[1] == 128
        assert X.shape[2] == 40
        assert len(y) == len(X)
