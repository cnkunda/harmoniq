"""Tests for deterministic jam grading (Commit 160)."""

from __future__ import annotations

import pytest

from app.jam_scoring import (
    compute_jam_grade,
    fallback_phrase_suggestion,
    grade_from_score,
    score_phrase,
)
from app.schemas import JamPhraseMetrics


def make_phrase(**overrides) -> JamPhraseMetrics:
    data = {
        "duration_ms": 1000,
        "notes_per_second": 2.5,
        "unique_pitch_classes": 7,
        "midi_span": 12,
        "contour": "mixed",
        "beat_offset_mean": 0.0,
        "beat_offset_std": 0.0,
        "note_count": 3,
        "intonation_cents": 0.0,
    }
    data.update(overrides)
    return JamPhraseMetrics(**data)


class TestGradeBoundaries:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (100.0, "A"),
            (90.0, "A"),
            (89.99, "B"),
            (80.0, "B"),
            (79.99, "C"),
            (70.0, "C"),
            (69.99, "D"),
            (60.0, "D"),
            (59.99, "F"),
            (0.0, "F"),
        ],
    )
    def test_thresholds(self, score: float, expected: str):
        assert grade_from_score(score) == expected

    def test_no_phrases_is_f(self):
        result = compute_jam_grade([])
        assert result.grade == "F"
        assert result.grade_score == 0.0
        assert result.weakest_phrase_index is None
        assert result.grade_breakdown == {}


class TestPhraseScoring:
    def test_perfect_phrase_scores_100(self):
        result = score_phrase(make_phrase())
        assert result.score == pytest.approx(100.0)
        assert set(result.components) == {
            "intonation",
            "timing",
            "pitch_variety",
            "melodic_range",
            "density",
        }

    def test_missing_intonation_is_normalized_not_capped(self):
        result = score_phrase(make_phrase(intonation_cents=None))
        # The 30 intonation points are absent, so the remaining 70-point
        # maximum normalizes to 100 instead of capping the phrase at 70.
        assert "intonation" not in result.components
        assert result.score == pytest.approx(100.0)

    def test_component_edges(self):
        result = score_phrase(
            make_phrase(
                intonation_cents=50.0,
                beat_offset_std=80.0,
                unique_pitch_classes=0,
                midi_span=0,
                notes_per_second=0.0,
            )
        )
        assert result.score == 0.0


class TestOverallGrade:
    def test_duration_weighted_score(self):
        strong = make_phrase(duration_ms=1000)
        weak = make_phrase(
            duration_ms=3000,
            intonation_cents=50.0,
            beat_offset_std=80.0,
            unique_pitch_classes=0,
            midi_span=0,
            notes_per_second=0.0,
        )
        result = compute_jam_grade([strong, weak])
        assert result.grade_score == pytest.approx(25.0)
        assert result.grade == "F"

    def test_weakest_index_and_tie(self):
        first = make_phrase(intonation_cents=40.0)
        second = make_phrase(intonation_cents=40.0)
        third = make_phrase(intonation_cents=0.0)
        result = compute_jam_grade([first, second, third])
        assert result.weakest_phrase_index == 0

        weaker = make_phrase(intonation_cents=50.0)
        result = compute_jam_grade([first, weaker, third])
        assert result.weakest_phrase_index == 1

    def test_breakdown_is_component_percentage(self):
        result = compute_jam_grade([make_phrase()])
        assert result.grade_breakdown == {
            "intonation": 100.0,
            "timing": 100.0,
            "pitch_variety": 100.0,
            "melodic_range": 100.0,
            "density": 100.0,
        }


class TestFallbackSuggestion:
    def test_always_returns_content(self):
        phrases = [
            make_phrase(),
            make_phrase(intonation_cents=40.0),
            make_phrase(beat_offset_mean=120.0),
            make_phrase(notes_per_second=5.0),
            make_phrase(unique_pitch_classes=2, midi_span=2, note_count=5),
            make_phrase(notes_per_second=0.2),
        ]
        for index, phrase in enumerate(phrases):
            assert fallback_phrase_suggestion(phrase, index).strip()
