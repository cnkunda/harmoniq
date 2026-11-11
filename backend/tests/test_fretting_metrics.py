"""Tests for W4 assignment metrics."""

from __future__ import annotations

import pytest

from app.fretting.assign import Assignment, assign_tab
from app.fretting.metrics import aggregate_metrics, evaluate_assignment
from app.fretting.tuning import standard
from app.fretting.types import TabNote


def _reference() -> list[TabNote]:
    return [
        TabNote(64, 0.0, 0.2, string=1, fret=0),
        TabNote(67, 0.2, 0.4, string=1, fret=3),
    ]


def _assignment(notes: list[TabNote]) -> Assignment:
    return assign_tab(notes, mode="baseline")


class TestEvaluate:
    def test_perfect_match(self) -> None:
        reference = _reference()
        metrics = evaluate_assignment(reference, _assignment(reference))
        assert metrics["pitch_accuracy"] == 1.0
        assert metrics["tab_accuracy"] == 1.0
        assert metrics["unassignable"] == 0

    def test_wrong_position_reduces_tab_accuracy(self) -> None:
        reference = [
            TabNote(67, 0.0, 0.2, string=2, fret=8),
            TabNote(67, 0.2, 0.4, string=2, fret=8),
        ]
        metrics = evaluate_assignment(reference, _assignment(reference))
        assert metrics["pitch_accuracy"] == 1.0
        assert metrics["tab_accuracy"] == 0.0

    def test_unassigned_counts_as_miss(self) -> None:
        reference = [
            TabNote(64, 0.0, 0.2, string=1, fret=0),
            TabNote(30, 0.2, 0.4, string=6, fret=0),
        ]
        metrics = evaluate_assignment(reference, _assignment(reference))
        assert metrics["assigned"] == 1
        assert metrics["pitch_accuracy"] == 0.5

    def test_difficulty_uses_transitions(self) -> None:
        reference = _reference()
        metrics = evaluate_assignment(reference, _assignment(reference))
        assert metrics["transitions"] == 1
        # (1,0) -> (1,3): 1.5 fret stretch + 0.75 locality = 2.25
        assert metrics["difficulty"] == pytest.approx(2.25)

    def test_misaligned_lengths_rejected(self) -> None:
        with pytest.raises(ValueError, match="align"):
            evaluate_assignment(_reference(), _assignment(_reference()[:1]))


class TestAggregate:
    def test_note_weighted_accuracy(self) -> None:
        results = [
            {
                "notes": 2,
                "assigned": 2,
                "tab_matches": 1,
                "difficulty": 1.0,
                "transitions": 1,
                "group_validity": None,
            },
            {
                "notes": 3,
                "assigned": 3,
                "tab_matches": 3,
                "difficulty": 2.0,
                "transitions": 2,
                "group_validity": 1.0,
            },
        ]
        aggregate = aggregate_metrics(results)
        assert aggregate["notes"] == 5
        assert aggregate["tab_matches"] == 4
        assert aggregate["tab_accuracy"] == pytest.approx(0.8)
        assert aggregate["difficulty"] == pytest.approx(1.5)
        assert aggregate["group_validity"] == 1.0

    def test_empty(self) -> None:
        aggregate = aggregate_metrics([])
        assert aggregate["tracks"] == 0
        assert aggregate["pitch_accuracy"] is None


class TestStandardTuningDefaults:
    def test_assignment_uses_standard_by_default(self) -> None:
        assignment = _assignment(_reference())
        assert assignment.tuning == standard()
