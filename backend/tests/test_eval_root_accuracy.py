"""Tests for the W3 GuitarSet root-accuracy metric."""

from __future__ import annotations

from app.evaluation.ground_truth import GTChord
from app.evaluation.metrics import chord_frame_accuracy, chord_root, chord_root_accuracy


class TestChordRoot:
    def test_root_parsing(self):
        assert chord_root("C:maj") == "C"
        assert chord_root("F#:min7") == "F#"
        assert chord_root("N") == "N"
        assert chord_root("") == "N"

    def test_quality_does_not_affect_root(self):
        reference = [GTChord(0.0, 2.0, "C:maj")]
        estimate = [GTChord(0.0, 2.0, "C:min")]
        frame = chord_frame_accuracy(reference, estimate)
        root = chord_root_accuracy(reference, estimate)
        assert frame["frame_accuracy"] == 0.0
        assert root["root_accuracy"] == 1.0

    def test_wrong_root_scores_zero(self):
        reference = [GTChord(0.0, 2.0, "C:maj")]
        estimate = [GTChord(0.0, 2.0, "D:maj")]
        root = chord_root_accuracy(reference, estimate)
        assert root["root_accuracy"] == 0.0

    def test_empty_reference_matches_frame_metric(self):
        root = chord_root_accuracy([], [GTChord(0.0, 1.0, "C:maj")])
        assert root["root_accuracy"] is None
        assert root["frames"] == 0
