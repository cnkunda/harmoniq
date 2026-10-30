"""Commit 184: calibration binning/ECE math tests (no MT3 inference)."""

from __future__ import annotations

import pytest

from app.chord_vocab import MIREX_TO_IDX
from app.confidence_calibration import (
    N_INDEX,
    bin_calibration,
    chord_to_mirex_index,
    expected_calibration_error,
    majority_gt_index,
)


class TestChordMapping:
    def test_keeps_mirex_labels(self):
        assert chord_to_mirex_index("C:maj") == MIREX_TO_IDX["C:maj"]
        assert chord_to_mirex_index("N") == N_INDEX

    def test_maps_277_labels_to_mirex(self):
        assert chord_to_mirex_index("C:maj7") == MIREX_TO_IDX["C:maj"]
        assert chord_to_mirex_index("C:min7") == MIREX_TO_IDX["C:min"]

    def test_unknown_label_is_no_chord(self):
        assert chord_to_mirex_index("not-a-chord") == N_INDEX


class TestMajorityGroundTruth:
    def test_picks_the_longest_overlap(self):
        intervals = [
            (0.0, 1.0, 1),
            (1.0, 3.0, 2),
        ]
        assert majority_gt_index(intervals, 0.5, 2.5) == (2, 1.5)

    def test_returns_no_chord_outside_the_timeline(self):
        assert majority_gt_index([(0.0, 1.0, 1)], 2.0, 3.0) == (N_INDEX, 0.0)

    def test_ignores_reversed_intervals(self):
        assert majority_gt_index([(0.0, 1.0, 1)], 2.0, 2.0) == (N_INDEX, 0.0)


class TestBinning:
    def test_perfectly_calibrated_data_has_zero_ece(self):
        bins = bin_calibration([0.0, 1.0], [0.0, 1.0], [1.0, 1.0])
        assert expected_calibration_error(bins) == pytest.approx(0.0)

    def test_overconfident_data_reports_the_gap(self):
        bins = bin_calibration([1.0, 1.0], [0.0, 1.0], [1.0, 1.0])
        assert expected_calibration_error(bins) == pytest.approx(0.5)

    def test_weights_duration_not_sample_count(self):
        bins = bin_calibration([0.9, 0.2], [0.0, 1.0], [1.0, 9.0])
        assert expected_calibration_error(bins) == pytest.approx(0.81)

    def test_empty_bins_are_kept_but_do_not_contribute(self):
        bins = bin_calibration([0.95], [1.0], [2.0], num_bins=10)
        assert len(bins) == 10
        assert bins[0].count == 0
        assert bins[-1].count == 1
        assert expected_calibration_error(bins) == pytest.approx(0.05)

    def test_empty_input_has_zero_ece(self):
        assert bin_calibration([], [], []) == []
        assert expected_calibration_error([]) == 0.0

    def test_invalid_inputs_fail_loudly(self):
        with pytest.raises(ValueError):
            bin_calibration([0.5], [1.0], [])
        with pytest.raises(ValueError):
            bin_calibration([float("nan")], [1.0], [1.0])
        with pytest.raises(ValueError):
            bin_calibration([0.5], [1.0], [-1.0])
        with pytest.raises(ValueError):
            bin_calibration([0.5], [1.0], [1.0], num_bins=0)
