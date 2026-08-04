"""Tests for label noise analysis (Commit 102).

Covers: synthetic sequence generation, temporal jitter, F1 computation,
noise detection, per-quality metrics, label quality gate, and report generation.
"""

from __future__ import annotations

import numpy as np
import pytest

# Import from the script directly (avoid TF import by using the module's functions)
import sys
from pathlib import Path

# Add scripts dir to path so we can import the module
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

# We need to mock the environment before importing
import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

from analyze_label_noise import (
    ROOT_NOTES,
    CHORD_VOCAB,
    VOCAB_SIZE,
    CHORD_QUALITIES,
    TOLERANCES_S,
    generate_synthetic_chord_sequence,
    apply_temporal_jitter,
    compute_chord_f1_at_tolerance,
    compute_f1_vs_tolerance,
    detect_label_noise_significance,
    compute_per_quality_f1,
    label_quality_gate,
    apply_jitter_augmentation,
    generate_report,
    _chord_root,
    _chord_quality,
    _chord_root_idx,
)


# ---------------------------------------------------------------------------
# Vocabulary helpers
# ---------------------------------------------------------------------------

class TestChordHelpers:
    def test_chord_root(self):
        assert _chord_root("C:maj") == "C"
        assert _chord_root("G:min7") == "G"
        assert _chord_root("N") == "N"

    def test_chord_quality(self):
        assert _chord_quality("C:maj") == "maj"
        assert _chord_quality("D:min7") == "min7"
        assert _chord_quality("N") == "N"

    def test_chord_root_idx(self):
        assert _chord_root_idx("C:maj") == 0
        assert _chord_root_idx("F#:min") == 6
        assert _chord_root_idx("N") == -1

    def test_vocab_size(self):
        assert VOCAB_SIZE == 277


# ---------------------------------------------------------------------------
# Synthetic sequence generation
# ---------------------------------------------------------------------------

class TestSyntheticSequence:
    def test_generates_correct_length(self):
        seq = generate_synthetic_chord_sequence(n_beats=20, beat_duration_s=0.5)
        assert len(seq) == 20
        assert all("chord" in e for e in seq)
        assert all("start_s" in e for e in seq)
        assert all("end_s" in e for e in seq)

    def test_beats_are_contiguous(self):
        seq = generate_synthetic_chord_sequence(n_beats=10, beat_duration_s=0.5)
        for i in range(1, len(seq)):
            assert seq[i]["start_s"] == pytest.approx(seq[i - 1]["end_s"], abs=1e-4)

    def test_chords_are_valid(self):
        seq = generate_synthetic_chord_sequence(n_beats=16)
        for e in seq:
            assert e["chord"] in CHORD_VOCAB

    def test_different_keys(self):
        seq_c = generate_synthetic_chord_sequence(n_beats=8, key_root=0)
        seq_g = generate_synthetic_chord_sequence(n_beats=8, key_root=7)
        # Different keys should produce different chord distributions
        chords_c = [e["chord"] for e in seq_c]
        chords_g = [e["chord"] for e in seq_g]
        # At least some chords should differ
        assert chords_c != chords_g

    def test_random_seed_reproducibility(self):
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        seq1 = generate_synthetic_chord_sequence(n_beats=16, rng=rng1)
        seq2 = generate_synthetic_chord_sequence(n_beats=16, rng=rng2)
        assert [e["chord"] for e in seq1] == [e["chord"] for e in seq2]


# ---------------------------------------------------------------------------
# Temporal jitter
# ---------------------------------------------------------------------------

class TestTemporalJitter:
    def test_zero_jitter_unchanged(self):
        seq = generate_synthetic_chord_sequence(n_beats=8)
        jittered = apply_temporal_jitter(seq, jitter_ms=0.0)
        for orig, j in zip(seq, jittered):
            assert orig["start_s"] == j["start_s"]
            assert orig["end_s"] == j["end_s"]

    def test_jitter_shifts_boundaries(self):
        seq = generate_synthetic_chord_sequence(n_beats=8)
        rng = np.random.default_rng(42)
        jittered = apply_temporal_jitter(seq, jitter_ms=30.0, rng=rng)
        # At least some boundaries should have shifted
        shifted = any(
            abs(orig["start_s"] - j["start_s"]) > 0.001
            for orig, j in zip(seq, jittered)
        )
        assert shifted

    def test_jitter_stays_positive(self):
        seq = generate_synthetic_chord_sequence(n_beats=8)
        rng = np.random.default_rng(42)
        jittered = apply_temporal_jitter(seq, jitter_ms=50.0, rng=rng)
        for e in jittered:
            assert e["start_s"] >= 0.0
            assert e["end_s"] > e["start_s"]


# ---------------------------------------------------------------------------
# F1 computation
# ---------------------------------------------------------------------------

class TestF1Computation:
    def test_perfect_predictions(self):
        gt = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:maj", "start_s": 0.5, "end_s": 1.0},
        ]
        pred = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:maj", "start_s": 0.5, "end_s": 1.0},
        ]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050)
        assert metrics["f1"] == 1.0
        assert metrics["tp"] == 2
        assert metrics["fp"] == 0
        assert metrics["fn"] == 0

    def test_no_predictions(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        pred = []
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050)
        assert metrics["f1"] == 0.0
        assert metrics["tp"] == 0
        assert metrics["fn"] == 1

    def test_no_ground_truth(self):
        gt = []
        pred = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050)
        assert metrics["f1"] == 0.0
        assert metrics["tp"] == 0
        assert metrics["fp"] == 1

    def test_timing_mismatch(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        # Prediction is 1 second off — should not match at 50ms tolerance
        pred = [{"chord": "C:maj", "start_s": 1.0, "end_s": 1.5}]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050)
        assert metrics["f1"] == 0.0

    def test_timing_within_tolerance(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        # Prediction is 30ms off — should match at 50ms tolerance
        pred = [{"chord": "C:maj", "start_s": 0.030, "end_s": 0.530}]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050)
        assert metrics["f1"] == 1.0

    def test_root_only_matching(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        # Different quality but same root
        pred = [{"chord": "C:min", "start_s": 0.0, "end_s": 0.5}]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050, root_only=True)
        assert metrics["f1"] == 1.0  # Root matches

    def test_quality_mismatch(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        pred = [{"chord": "C:min", "start_s": 0.0, "end_s": 0.5}]
        metrics = compute_chord_f1_at_tolerance(pred, gt, tolerance_s=0.050, root_only=False)
        assert metrics["f1"] == 0.0  # Quality doesn't match


# ---------------------------------------------------------------------------
# F1 vs tolerance curve
# ---------------------------------------------------------------------------

class TestF1VsTolerance:
    def test_returns_all_tolerances(self):
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        pred = [{"chord": "C:maj", "start_s": 0.030, "end_s": 0.530}]
        curve = compute_f1_vs_tolerance(pred, gt)
        assert len(curve) == len(TOLERANCES_S)
        assert all("tolerance_ms" in r for r in curve)
        assert all("f1" in r for r in curve)

    def test_f1_increases_with_tolerance(self):
        # Prediction is 30ms off — should fail at 10ms but pass at 50ms
        gt = [{"chord": "C:maj", "start_s": 0.0, "end_s": 0.5}]
        pred = [{"chord": "C:maj", "start_s": 0.030, "end_s": 0.530}]
        curve = compute_f1_vs_tolerance(pred, gt)
        f1_10ms = next(r["f1"] for r in curve if r["tolerance_ms"] == 10.0)
        f1_50ms = next(r["f1"] for r in curve if r["tolerance_ms"] == 50.0)
        assert f1_10ms < f1_50ms


# ---------------------------------------------------------------------------
# Noise detection
# ---------------------------------------------------------------------------

class TestNoiseDetection:
    def test_no_noise_detected(self):
        # Flat curve: F1 barely increases
        curve = [
            {"tolerance_ms": 10.0, "f1": 0.90},
            {"tolerance_ms": 25.0, "f1": 0.91},
            {"tolerance_ms": 50.0, "f1": 0.92},
            {"tolerance_ms": 100.0, "f1": 0.92},
            {"tolerance_ms": 200.0, "f1": 0.93},
            {"tolerance_ms": 500.0, "f1": 0.93},
        ]
        result = detect_label_noise_significance(curve)
        assert result["has_timing_noise"] is False

    def test_noise_detected(self):
        # Climbing curve: F1 improves significantly
        curve = [
            {"tolerance_ms": 10.0, "f1": 0.50},
            {"tolerance_ms": 25.0, "f1": 0.60},
            {"tolerance_ms": 50.0, "f1": 0.70},
            {"tolerance_ms": 100.0, "f1": 0.80},
            {"tolerance_ms": 200.0, "f1": 0.85},
            {"tolerance_ms": 500.0, "f1": 0.90},
        ]
        result = detect_label_noise_significance(curve)
        assert result["has_timing_noise"] is True
        assert result["f1_gain_50_to_500"] > 0.10

    def test_empty_curve(self):
        result = detect_label_noise_significance([])
        assert result["has_timing_noise"] is False


# ---------------------------------------------------------------------------
# Per-quality F1
# ---------------------------------------------------------------------------

class TestPerQualityF1:
    def test_triads_only(self):
        gt = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:min", "start_s": 0.5, "end_s": 1.0},
        ]
        pred = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:min", "start_s": 0.5, "end_s": 1.0},
        ]
        result = compute_per_quality_f1(pred, gt, tolerance_s=0.050)
        assert result["triad"]["f1"] == 1.0
        assert result["triad"]["count"] == 2

    def test_extended_chords(self):
        gt = [
            {"chord": "C:maj7", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:min7", "start_s": 0.5, "end_s": 1.0},
        ]
        pred = [
            {"chord": "C:maj7", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:min7", "start_s": 0.5, "end_s": 1.0},
        ]
        result = compute_per_quality_f1(pred, gt, tolerance_s=0.050)
        assert result["extended"]["f1"] == 1.0
        assert result["extended"]["count"] == 2


# ---------------------------------------------------------------------------
# Label quality gate
# ---------------------------------------------------------------------------

class TestLabelQualityGate:
    def test_rejects_short_chords(self):
        events = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.050},  # 50ms — too short
            {"chord": "G:maj", "start_s": 0.5, "end_s": 1.0},    # 500ms — fine
        ]
        accepted, rejected = label_quality_gate(events, max_jitter_ms=100.0)
        assert len(accepted) == 1
        assert len(rejected) == 1

    def test_rejects_overlapping(self):
        events = [
            {"chord": "C:maj", "start_s": 0.5, "end_s": 0.3},  # Overlap
            {"chord": "G:maj", "start_s": 0.0, "end_s": 0.5},  # Fine
        ]
        accepted, rejected = label_quality_gate(events, max_jitter_ms=100.0)
        assert len(accepted) == 1
        assert len(rejected) == 1

    def test_accepts_normal_chords(self):
        events = [
            {"chord": "C:maj", "start_s": 0.0, "end_s": 0.5},
            {"chord": "G:maj", "start_s": 0.5, "end_s": 1.0},
        ]
        accepted, rejected = label_quality_gate(events, max_jitter_ms=100.0)
        assert len(accepted) == 2
        assert len(rejected) == 0


# ---------------------------------------------------------------------------
# Jitter augmentation
# ---------------------------------------------------------------------------

class TestJitterAugmentation:
    def test_doubles_dataset_size(self):
        X = np.random.rand(10, 128, 40).astype(np.float32)
        y = np.arange(10, dtype=np.int32)
        rng = np.random.default_rng(42)
        # Use 200ms jitter to ensure max_frames >= 1
        X_aug, y_aug = apply_jitter_augmentation(X, y, jitter_ms=200.0, rng=rng)
        # Each sample gets an original + jittered copy
        assert len(X_aug) == 20
        assert len(y_aug) == 20

    def test_preserves_labels(self):
        X = np.random.rand(5, 128, 40).astype(np.float32)
        y = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        rng = np.random.default_rng(42)
        X_aug, y_aug = apply_jitter_augmentation(X, y, jitter_ms=200.0, rng=rng)
        # Labels are interleaved: [orig_0, jitter_0, orig_1, jitter_1, ...]
        for i in range(5):
            assert y_aug[i * 2] == y[i]  # Original
            assert y_aug[i * 2 + 1] == y[i]  # Jittered copy

    def test_zero_jitter_no_change(self):
        X = np.random.rand(5, 128, 40).astype(np.float32)
        y = np.arange(5, dtype=np.int32)
        X_aug, y_aug = apply_jitter_augmentation(X, y, jitter_ms=0.0)
        np.testing.assert_array_equal(X_aug, X)
        np.testing.assert_array_equal(y_aug, y)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:
    def test_generates_valid_markdown(self):
        f1_curves = {
            "clean": [
                {"tolerance_ms": 10.0, "f1": 0.5, "precision": 0.5, "recall": 0.5, "tp": 10, "fp": 10, "fn": 10},
                {"tolerance_ms": 50.0, "f1": 0.8, "precision": 0.8, "recall": 0.8, "tp": 16, "fp": 4, "fn": 4},
                {"tolerance_ms": 500.0, "f1": 0.9, "precision": 0.9, "recall": 0.9, "tp": 18, "fp": 2, "fn": 2},
            ],
        }
        noise_detections = {
            "clean": {
                "has_timing_noise": False,
                "f1_gain_50_to_500": 0.125,
                "recommendation": "Test recommendation.",
            },
        }
        per_quality = {
            "triad": {"f1": 0.8, "precision": 0.8, "recall": 0.8, "tp": 16, "fp": 4, "fn": 4, "count": 20},
        }

        report = generate_report(f1_curves, noise_detections, per_quality)
        assert "# Label Quality Analysis Report" in report
        assert "| Tolerance (ms) |" in report
        assert "triad" in report
        assert "MT3" in report

    def test_report_contains_required_sections(self):
        report = generate_report({}, {}, {})
        assert "Threshold Sensitivity Analysis" in report
        assert "Noise Detection" in report
        assert "Per-Quality-Group" in report
        assert "Label Quality Gate" in report
        assert "Methodology" in report
