"""Tests for the W4 string-activity target prototype."""

from __future__ import annotations

import numpy as np
import pytest

from app.fretting.string_activity import (
    build_string_activity_targets,
    string_activity_summary,
)
from app.fretting.types import TabNote


class TestTargets:
    def test_two_strings(self) -> None:
        notes = [
            TabNote(64, 0.0, 0.3, string=1, fret=0),
            TabNote(40, 0.2, 0.5, string=6, fret=0),
        ]
        matrix = build_string_activity_targets(notes, hop_s=0.1)
        assert matrix.shape == (5, 6)
        assert matrix[:3, 0].tolist() == [1.0, 1.0, 1.0]
        assert matrix[2:, 5].tolist() == [1.0, 1.0, 1.0]

    def test_ignores_unassigned_notes(self) -> None:
        notes = [TabNote(64, 0.0, 0.2)]
        matrix = build_string_activity_targets(notes, duration_s=0.2)
        assert matrix.shape == (2, 6)
        assert not matrix.any()

    def test_empty_notes(self) -> None:
        matrix = build_string_activity_targets([], duration_s=0.0)
        assert matrix.shape == (0, 6)

    def test_invalid_string(self) -> None:
        notes = [TabNote(64, 0.0, 0.2, string=7, fret=0)]
        with pytest.raises(ValueError, match="string must be"):
            build_string_activity_targets(notes, duration_s=0.2)

    def test_invalid_hop(self) -> None:
        with pytest.raises(ValueError, match="hop_s"):
            build_string_activity_targets([], hop_s=0.0)


class TestSummary:
    def test_fractions(self) -> None:
        matrix = np.zeros((4, 6), dtype=np.float32)
        matrix[:, 0] = [1, 1, 0, 0]
        summary = string_activity_summary(matrix)
        assert summary["string_1"] == 0.5
        assert summary["string_6"] == 0.0

    def test_empty_matrix(self) -> None:
        summary = string_activity_summary(np.zeros((0, 6), dtype=np.float32))
        assert summary["string_1"] == 0.0

    def test_bad_shape(self) -> None:
        with pytest.raises(ValueError, match="expected a"):
            string_activity_summary(np.zeros((3, 4), dtype=np.float32))
