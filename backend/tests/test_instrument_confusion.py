"""Commit 121: Instrument confusion diagnostic tests."""

from __future__ import annotations

import pytest
from app.instrument_confusion import compute_per_section_confusion
from app.schemas import (
    ChordEvent,
    ChordTimeline,
    LessonSectionStub,
    SectionConfusionScore,
)


def _make_timeline(events: list[tuple[float, str, float]]) -> ChordTimeline:
    return ChordTimeline(events=[
        ChordEvent(timestamp=t, chord=c, confidence=conf) for t, c, conf in events
    ])


def _make_section(*, label: str, start: float | None, end: float | None) -> LessonSectionStub:
    return LessonSectionStub(
        label=label,
        confidence=0.6,
        start_time_seconds=start,
        end_time_seconds=end,
    )


class TestComputePerSectionConfusion:
    """Tests for the compute_per_section_confusion helper."""

    def test_empty_fusion_log_returns_empty_list(self):
        sections = [_make_section(label="Intro", start=0.0, end=10.0)]
        tl = _make_timeline([(1.0, "C:maj", 0.9)])
        result = compute_per_section_confusion(sections, tl, [])
        assert result == []

    def test_empty_sections_returns_empty_list(self):
        result = compute_per_section_confusion([], None, [{"timestamp": 1.0}])
        assert result == []

    def test_no_chord_timeline_returns_empty_list(self):
        sections = [_make_section(label="Intro", start=0.0, end=10.0)]
        result = compute_per_section_confusion(sections, None, [{"timestamp": 1.0}])
        assert result == []

    def test_no_disagreements(self):
        sections = [_make_section(label="A", start=0.0, end=10.0)]
        tl = _make_timeline([(1.0, "C:maj", 0.9), (2.0, "G:maj", 0.8)])
        result = compute_per_section_confusion(sections, tl, [])
        assert result == []

    def test_single_section_full_disagreement(self):
        """All beats disagree within a single section."""
        sections = [_make_section(label="Verse", start=0.0, end=5.0)]
        tl = _make_timeline([
            (1.0, "C:maj", 0.9),
            (2.0, "G:maj", 0.8),
            (3.0, "Am:min", 0.7),
        ])
        fusion_log = [
            {"timestamp": 1.0, "stem_chord": "C:maj", "mix_chord": "F:maj"},
            {"timestamp": 2.0, "stem_chord": "G:maj", "mix_chord": "D:maj"},
            {"timestamp": 3.0, "stem_chord": "Am:min", "mix_chord": "Em:min"},
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 1
        assert result[0].instrument_confusion == 1.0
        assert result[0].is_high_confusion is True
        assert result[0].beat_count == 3
        assert result[0].disagreement_count == 3

    def test_single_section_partial_disagreement(self):
        """Half of beats disagree within a single section."""
        sections = [_make_section(label="Verse", start=0.0, end=5.0)]
        tl = _make_timeline([
            (1.0, "C:maj", 0.9),
            (2.0, "G:maj", 0.8),
            (3.0, "Am:min", 0.7),
            (4.0, "F:maj", 0.6),
        ])
        fusion_log = [
            {"timestamp": 1.0, "stem_chord": "C:maj", "mix_chord": "F:maj"},
            {"timestamp": 3.0, "stem_chord": "Am:min", "mix_chord": "C:maj"},
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 1
        assert result[0].instrument_confusion == 0.5
        assert result[0].beat_count == 4
        assert result[0].disagreement_count == 2

    def test_low_confusion_not_flagged_as_high(self):
        """Confusion below 0.3 is not flagged as high."""
        sections = [_make_section(label="Intro", start=0.0, end=6.0)]
        tl = _make_timeline([
            (1.0, "C:maj", 0.9),
            (2.0, "G:maj", 0.8),
            (3.0, "Am:min", 0.7),
            (4.0, "F:maj", 0.6),
            (5.0, "C:maj", 0.9),
        ])
        fusion_log = [
            {"timestamp": 4.0, "stem_chord": "F:maj", "mix_chord": "D:maj"},
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 1
        assert result[0].instrument_confusion == 0.2
        assert result[0].is_high_confusion is False

    def test_high_confusion_flagged(self):
        """Confusion above 0.3 is flagged as high."""
        sections = [_make_section(label="Chorus", start=0.0, end=5.0)]
        tl = _make_timeline([
            (1.0, "C:maj", 0.9),
            (2.0, "G:maj", 0.8),
            (3.0, "Am:min", 0.7),
        ])
        fusion_log = [
            {"timestamp": 1.0, "stem_chord": "C:maj", "mix_chord": "F:maj"},
            {"timestamp": 2.0, "stem_chord": "G:maj", "mix_chord": "D:maj"},
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 1
        assert abs(result[0].instrument_confusion - 2 / 3) < 0.001
        assert result[0].is_high_confusion is True

    def test_per_section_different_confusion_levels(self):
        """Each section gets its own confusion score."""
        sections = [
            _make_section(label="Intro", start=0.0, end=2.0),
            _make_section(label="Verse", start=2.0, end=5.0),
        ]
        tl = _make_timeline([
            (0.5, "C:maj", 0.9),
            (1.0, "G:maj", 0.8),
            (2.5, "Am:min", 0.7),
            (3.0, "F:maj", 0.6),
        ])
        fusion_log = [
            # One disagreement in Intro (out of 2 events)
            {"timestamp": 0.5, "stem_chord": "C:maj", "mix_chord": "F:maj"},
            # No disagreements in Verse (2 events, 0 disagreements)
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 2
        assert result[0].section_index == 0
        assert result[0].instrument_confusion == 0.5
        assert result[0].beat_count == 2
        assert result[0].disagreement_count == 1
        assert result[1].section_index == 1
        assert result[1].instrument_confusion == 0.0
        assert result[1].beat_count == 2
        assert result[1].disagreement_count == 0

    def test_event_outside_any_section_is_excluded(self):
        """Events before the first section start are excluded from counting."""
        sections = [_make_section(label="Body", start=2.0, end=5.0)]
        tl = _make_timeline([
            (0.5, "C:maj", 0.9),  # before section, should be excluded
            (2.5, "G:maj", 0.8),
            (3.0, "Am:min", 0.7),
        ])
        fusion_log = [
            {"timestamp": 0.5, "stem_chord": "C:maj", "mix_chord": "F:maj"},  # excluded
            {"timestamp": 2.5, "stem_chord": "G:maj", "mix_chord": "D:maj"},
        ]
        result = compute_per_section_confusion(sections, tl, fusion_log)
        assert len(result) == 1
        assert result[0].beat_count == 2
        assert result[0].disagreement_count == 1
        assert result[0].instrument_confusion == 0.5

    def test_section_label_fallback(self):
        """Sections with no label fall back to 'Section N'."""
        sec = LessonSectionStub(
            label=None,
            confidence=0.6,
            start_time_seconds=0.0,
        )
        tl = _make_timeline([(1.0, "C:maj", 0.9)])
        fusion_log = [{"timestamp": 1.0, "stem_chord": "C:maj", "mix_chord": "F:maj"}]
        result = compute_per_section_confusion([sec], tl, fusion_log)
        assert result[0].label == "Section 1"


class TestSectionConfusionScoreSchema:
    """Tests for the SectionConfusionScore Pydantic model."""

    def test_minimal_construction(self):
        score = SectionConfusionScore(
            section_index=0,
            label="Intro",
            instrument_confusion=0.0,
            beat_count=0,
            disagreement_count=0,
        )
        assert score.section_index == 0
        assert score.instrument_confusion == 0.0
        assert score.is_high_confusion is False

    def test_high_confusion_auto_flag(self):
        """is_high_confusion must be explicitly set, not auto-derived."""
        score = SectionConfusionScore(
            section_index=0,
            label="Chorus",
            instrument_confusion=0.35,
            is_high_confusion=True,
            beat_count=10,
            disagreement_count=4,
        )
        assert score.is_high_confusion is True

    def test_confusion_clamped_to_zero_one(self):
        """instrument_confusion should be validated to 0-1 range."""
        with pytest.raises(Exception):
            SectionConfusionScore(
                section_index=0,
                label="Bad",
                instrument_confusion=-0.1,
                beat_count=1,
                disagreement_count=0,
            )
        with pytest.raises(Exception):
            SectionConfusionScore(
                section_index=0,
                label="Bad",
                instrument_confusion=1.5,
                beat_count=1,
                disagreement_count=0,
            )


class TestInstrumentConfusionScoring:
    """Tests for how instrument confusion affects scoring reliability.

    Note: these tests require librosa. They are guarded with try/except
    to avoid blocking the rest of the test suite when librosa is unavailable.
    """

    def test_high_confusion_adds_flag(self):
        """High instrument confusion (>0.3) adds reliability flag."""
        try:
            from app.score import _coach_paragraph_from_score
        except ModuleNotFoundError:
            pytest.skip("librosa not available")
        flags = ["high_instrument_confusion"]
        paragraph = _coach_paragraph_from_score(0.8, 0.8, 0.8, "high", flags, "technique")
        assert "instrument" in paragraph.lower()
        assert "interfering" in paragraph.lower()

    def test_low_confusion_does_not_add_flag(self):
        """Low instrument confusion should not produce hedging text."""
        try:
            from app.score import _coach_paragraph_from_score
        except ModuleNotFoundError:
            pytest.skip("librosa not available")
        paragraph = _coach_paragraph_from_score(0.8, 0.8, 0.8, "high", [], "technique")
        assert "instrument" not in paragraph.lower()
        assert "interfering" not in paragraph.lower()

    def test_very_high_confusion_downgrades_confidence(self):
        """Instrument confusion >0.5 should downgrade confidence to low."""
        from app.schemas import ScoreRequest

        req = ScoreRequest(
            recording_wav_base64="",
            recording_mime_type="audio/wav",
            section={"tempo": 80.0, "key": "C major"},
            skill_nodes=["pitch_accuracy"],
            instrument_confusion=0.6,
        )
        assert req.instrument_confusion == 0.6
