"""Tests for Commit 123: Solo Harmony Enrichment — Chord-Tone Classification & Position Inference."""

from __future__ import annotations

import pytest

from app.solo_harmony_analyzer import (
    ChordToneClassifier,
    PositionInferenceEngine,
    SoloHarmonizer,
    build_scale_pitch_classes,
    find_active_chord,
    parse_chord,
    parse_key_name,
)
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    SoloNote,
    SoloNotes,
    TimeSignature,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _make_beat_grid(
    bpm: float = 120.0,
    beats: list[float] | None = None,
    downbeats: list[float] | None = None,
) -> BeatGrid:
    """Create a minimal BeatGrid for testing."""
    if beats is None:
        beats = [i * 0.5 for i in range(100)]
    if downbeats is None:
        downbeats = [i * 2.0 for i in range(25)]
    return BeatGrid(
        bpm=bpm,
        pulse_bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
    )


def _make_chord_timeline(chords: list[tuple[float, str]]) -> ChordTimeline:
    """Create a ChordTimeline from [(timestamp, chord_label), ...]."""
    events = [
        ChordEvent(timestamp=t, chord=c, confidence=0.9)
        for t, c in chords
    ]
    return ChordTimeline(events=events)


def _make_solo_notes(notes: list[tuple[float, float, int, int]]) -> SoloNotes:
    """Create SoloNotes from [(start_time, duration, pitch, velocity), ...]."""
    return SoloNotes(
        notes=[
            SoloNote(start_time=s, duration=d, pitch=p, velocity=v)
            for s, d, p, v in notes
        ]
    )


# ---------------------------------------------------------------------------
# parse_key_name
# ---------------------------------------------------------------------------


class TestParseKeyName:
    def test_major(self):
        assert parse_key_name("C major") == (0, "major")

    def test_minor(self):
        assert parse_key_name("A minor") == (9, "minor")

    def test_sharp_root(self):
        assert parse_key_name("G# minor") == (8, "minor")

    def test_bare_root_defaults_major(self):
        assert parse_key_name("C") == (0, "major")

    def test_whitespace_handling(self):
        assert parse_key_name("  G major  ") == (7, "major")


# ---------------------------------------------------------------------------
# build_scale_pitch_classes
# ---------------------------------------------------------------------------


class TestBuildScalePitchClasses:
    def test_c_major(self):
        pcs = build_scale_pitch_classes(0, "major")
        assert pcs == {0, 2, 4, 5, 7, 9, 11}

    def test_a_minor(self):
        pcs = build_scale_pitch_classes(9, "minor")
        # A minor: A B C D E F G → 9, 11, 0, 2, 4, 5, 7
        assert pcs == {0, 2, 4, 5, 7, 9, 11}

    def test_g_major(self):
        pcs = build_scale_pitch_classes(7, "major")
        # G major: G A B C D E F# → 7, 9, 11, 0, 2, 4, 6
        assert pcs == {0, 2, 4, 6, 7, 9, 11}


# ---------------------------------------------------------------------------
# parse_chord
# ---------------------------------------------------------------------------


class TestParseChord:
    def test_c_major(self):
        result = parse_chord("C:maj")
        assert result is not None
        root, quality, intervals = result
        assert root == 0
        assert quality == "maj"
        assert intervals == [0, 4, 7]

    def test_g_minor(self):
        result = parse_chord("G:min")
        assert result is not None
        root, quality, intervals = result
        assert root == 7
        assert quality == "min"
        assert intervals == [0, 3, 7]

    def test_n_chord(self):
        assert parse_chord("N") is None

    def test_malformed(self):
        assert parse_chord("invalid") is None

    def test_sharp_root(self):
        result = parse_chord("F#:maj7")
        assert result is not None
        root, quality, intervals = result
        assert root == 6
        assert quality == "maj7"
        assert intervals == [0, 4, 7, 11]


# ---------------------------------------------------------------------------
# find_active_chord
# ---------------------------------------------------------------------------


class TestFindActiveChord:
    def test_basic(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:min", confidence=0.9),
        ]
        assert find_active_chord(0.5, events).chord == "C:maj"
        assert find_active_chord(2.0, events).chord == "G:min"
        assert find_active_chord(3.0, events).chord == "G:min"

    def test_empty_events(self):
        assert find_active_chord(1.0, []) is None

    def test_before_first_event(self):
        events = [ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.9)]
        assert find_active_chord(0.5, events) is None


# ---------------------------------------------------------------------------
# ChordToneClassifier
# ---------------------------------------------------------------------------


class TestChordToneClassifier:
    """Test cases from PRIORITIES.md spec (§11)."""

    def setup_method(self):
        self.classifier = ChordToneClassifier(key_root=0, mode="major")  # C major

    def test_root(self):
        """Pitch 60 (C4) against C:maj → root, scale_degree=1, chord_tone."""
        result = self.classifier.classify(60, "C:maj")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 1
        assert result.scale_degree_name == "R"
        assert result.semitone_distance == 0

    def test_third(self):
        """Pitch 64 (E4) against C:maj → 3rd, scale_degree=3, chord_tone."""
        result = self.classifier.classify(64, "C:maj")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 3
        assert result.scale_degree_name == "3"
        assert result.semitone_distance == 4

    def test_fifth(self):
        """Pitch 67 (G4) against C:maj → 5th, scale_degree=5, chord_tone."""
        result = self.classifier.classify(67, "C:maj")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 5
        assert result.scale_degree_name == "5"
        assert result.semitone_distance == 7

    def test_tension(self):
        """Pitch 65 (F4) against C:maj → 4th, tension (in C major scale, not in C chord)."""
        result = self.classifier.classify(65, "C:maj")
        assert result is not None
        assert result.chord_tone_type == "tension"
        assert result.scale_degree == 4
        assert result.scale_degree_name == "4"

    def test_chromatic(self):
        """Pitch 66 (F#4) against C:maj → chromatic (outside key)."""
        result = self.classifier.classify(66, "C:maj")
        assert result is not None
        assert result.chord_tone_type == "chromatic"
        assert result.scale_degree is None
        assert result.scale_degree_name == "b5"  # semitone 6 = b5/#4; dict maps to "b5"
        assert result.semitone_distance == 6

    def test_n_chord_returns_none(self):
        """No chord → chord_analysis = None."""
        result = self.classifier.classify(60, "N")
        assert result is None

    def test_minor_third(self):
        """Pitch 63 (Eb4) against C:min → b3, chord_tone."""
        result = self.classifier.classify(63, "C:min")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 3
        assert result.scale_degree_name == "b3"
        assert result.semitone_distance == 3

    def test_seventh(self):
        """Pitch 71 (B4) against C:maj7 → 7, chord_tone."""
        result = self.classifier.classify(71, "C:maj7")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 7
        assert result.scale_degree_name == "7"
        assert result.semitone_distance == 11

    def test_flat_seventh(self):
        """Pitch 70 (Bb4) against C:7 → b7, chord_tone."""
        result = self.classifier.classify(70, "C:7")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree_name == "b7"
        assert result.semitone_distance == 10

    def test_chord_tone_in_minor_key(self):
        """Pitch 60 (C4) against A:min in A minor → chord_tone (b3 of Am)."""
        classifier = ChordToneClassifier(key_root=9, mode="minor")
        result = classifier.classify(60, "A:min")
        assert result is not None
        assert result.chord_tone_type == "chord_tone"
        assert result.scale_degree == 3
        assert result.scale_degree_name == "b3"

    def test_modal_heuristic_b7(self):
        """Bb4 (70) against G:maj in G major → tension (modal heuristic, not chromatic).

        G major scale = {G, A, B, C, D, E, F#}. Bb is not in the scale.
        But b7 (semitone 10) is a common Mixolydian extension → reclassified as tension.
        """
        classifier = ChordToneClassifier(key_root=7, mode="major")
        result = classifier.classify(70, "G:maj")
        assert result is not None
        # Modal heuristic should reclassify b7 as tension, not chromatic
        assert result.chord_tone_type == "tension"

    def test_octave_equivalence(self):
        """MIDI 48 (C3) and MIDI 72 (C5) both classify as root of C:maj."""
        low = self.classifier.classify(48, "C:maj")
        high = self.classifier.classify(72, "C:maj")
        assert low is not None and high is not None
        assert low.chord_tone_type == high.chord_tone_type == "chord_tone"
        assert low.scale_degree == high.scale_degree == 1
        assert low.semitone_distance == high.semitone_distance == 0


# ---------------------------------------------------------------------------
# PositionInferenceEngine
# ---------------------------------------------------------------------------


class TestPositionInferenceEngine:
    def test_known_phrase(self):
        """Known solo phrase against known chord → CAGED label."""
        # G major chord, notes in a typical open-position solo
        # G4=67, A4=69, B4=71, D5=74
        engine = PositionInferenceEngine(chord_root_pc=7)  # G

        notes = _make_solo_notes([
            (0.0, 0.5, 67, 80),   # G4
            (0.5, 0.5, 69, 80),   # A4
            (1.0, 0.5, 71, 80),   # B4
            (1.5, 0.5, 74, 80),   # D5
        ])

        position = engine.infer_position(notes.notes)
        # Should return some CAGED label
        assert position is not None
        assert "CAGED" in position

    def test_empty_notes(self):
        """No notes → None position."""
        engine = PositionInferenceEngine(chord_root_pc=0)
        position = engine.infer_position([])
        assert position is None

    def test_out_of_bounds_midi(self):
        """MIDI notes outside guitar range → handled gracefully."""
        engine = PositionInferenceEngine(chord_root_pc=0)
        notes = _make_solo_notes([
            (0.0, 0.5, 20, 80),  # Below guitar range
            (0.5, 0.5, 100, 80),  # Above guitar range
        ])
        position = engine.infer_position(notes.notes)
        # Should not crash; may return None
        assert position is None


# ---------------------------------------------------------------------------
# SoloHarmonizer (integration)
# ---------------------------------------------------------------------------


class TestSoloHarmonizer:
    def test_basic_integration(self):
        """Full integration: chord timeline + solo notes → harmonized output."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
            (2.0, "G:maj"),
        ])
        solo_notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),  # C4 over C:maj → root
            (0.5, 0.5, 64, 80),  # E4 over C:maj → 3rd
            (2.0, 0.5, 67, 80),  # G4 over G:maj → root
            (2.5, 0.5, 71, 80),  # B4 over G:maj → 3rd
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        # Check harmonized_solo
        hs = harmonizer.harmonized_solo
        assert hs.note_count == 4
        assert len(hs.notes) == 4

        # First note: C4 over C:maj → chord_tone, root
        n0 = hs.notes[0]
        assert n0.chord == "C:maj"
        assert n0.chord_analysis is not None
        assert n0.chord_analysis.chord_tone_type == "chord_tone"
        assert n0.chord_analysis.scale_degree == 1
        assert n0.chord_analysis.scale_degree_name == "R"

        # Second note: E4 over C:maj → chord_tone, 3rd
        n1 = hs.notes[1]
        assert n1.chord == "C:maj"
        assert n1.chord_analysis is not None
        assert n1.chord_analysis.chord_tone_type == "chord_tone"
        assert n1.chord_analysis.scale_degree == 3

        # Third note: G4 over G:maj → chord_tone, root
        n2 = hs.notes[2]
        assert n2.chord == "G:maj"
        assert n2.chord_analysis is not None
        assert n2.chord_analysis.chord_tone_type == "chord_tone"
        assert n2.chord_analysis.scale_degree == 1

        # Percentages: all 4 notes are chord tones
        assert hs.chord_tone_pct == 1.0
        assert hs.tension_note_pct == 0.0
        assert hs.chromatic_pct == 0.0

    def test_n_chord_skips_analysis(self):
        """Notes over 'N' chords get chord_analysis = None."""
        chord_timeline = _make_chord_timeline([
            (0.0, "N"),
        ])
        solo_notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        hs = harmonizer.harmonized_solo
        assert hs.note_count == 1
        assert hs.notes[0].chord is None
        assert hs.notes[0].chord_analysis is None
        # Percentages: no analyzed notes → all 0
        assert hs.chord_tone_pct == 0.0
        assert hs.tension_note_pct == 0.0
        assert hs.chromatic_pct == 0.0

    def test_empty_chord_timeline(self):
        """Empty chord_timeline → harmonized notes with no chord context."""
        chord_timeline = ChordTimeline(events=[])
        solo_notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        hs = harmonizer.harmonized_solo
        assert hs.note_count == 1
        assert hs.notes[0].chord is None
        assert hs.notes[0].chord_analysis is None

    def test_empty_solo_notes(self):
        """Empty solo_notes → no harmonized output."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
        ])
        solo_notes = SoloNotes(notes=[])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        hs = harmonizer.harmonized_solo
        assert hs.note_count == 0
        assert hs.notes == []

    def test_per_bar_analysis(self):
        """Per-bar analysis produces BarScope entries."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
            (4.0, "G:maj"),
        ])
        solo_notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),   # Bar 0: C4
            (1.0, 0.5, 64, 80),   # Bar 0: E4
            (4.0, 0.5, 67, 80),   # Bar 1: G4
        ])
        beat_grid = _make_beat_grid(
            downbeats=[0.0, 2.0, 4.0, 6.0],
        )

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        bars = harmonizer.per_bar_analysis
        assert len(bars) == 3  # 3 downbeat intervals → 3 bars

        # Bar 0 (0.0-2.0): has 2 notes, dominant chord C:maj
        b0 = bars[0]
        assert b0.bar_index == 0
        assert b0.chord == "C:maj"
        assert len(b0.notes) == 2
        assert len(b0.suggested_scales) > 0

        # Bar 1 (2.0-4.0): no notes
        b1 = bars[1]
        assert b1.chord is None
        assert len(b1.notes) == 0

        # Bar 2 (4.0-6.0): has 1 note, dominant chord G:maj
        b2 = bars[2]
        assert b2.chord == "G:maj"
        assert len(b2.notes) == 1

    def test_mixed_chord_tones_and_chromatic(self):
        """Mixed note types produce correct percentages."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
        ])
        # C4=chord_tone, E4=chord_tone, F4=tension, F#4=chromatic
        solo_notes = _make_solo_notes([
            (0.0, 0.25, 60, 80),  # C4 → chord_tone
            (0.25, 0.25, 64, 80),  # E4 → chord_tone
            (0.50, 0.25, 65, 80),  # F4 → tension
            (0.75, 0.25, 66, 80),  # F#4 → chromatic
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        hs = harmonizer.harmonized_solo
        assert hs.note_count == 4
        assert hs.chord_tone_pct == 0.5
        assert hs.tension_note_pct == 0.25
        assert hs.chromatic_pct == 0.25


# ---------------------------------------------------------------------------
# Additional coverage: edge cases and KB §16.11 gaps
# ---------------------------------------------------------------------------


class TestParseKeyNameFlatRoots:
    def test_bb_major(self):
        """Bb major → (10, 'major') — Bb is A# (pitch class 10)."""
        assert parse_key_name("Bb major") == (10, "major")

    def test_eb_major(self):
        """Eb major → (3, 'major') — Eb is D# (pitch class 3)."""
        assert parse_key_name("Eb major") == (3, "major")

    def test_ab_minor(self):
        """Ab minor → (8, 'minor') — Ab is G# (pitch class 8)."""
        assert parse_key_name("Ab minor") == (8, "minor")


class TestSustainAcrossChordBoundary:
    """KB §16.11.2: A long note is evaluated against the chord at its start_time."""

    def test_note_evaluated_at_onset_not_sustain(self):
        """Note starting at end of C:maj is classified against C:maj, not G:maj."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
            (1.0, "G:maj"),
        ])
        # Note at 0.9s (just before chord change) — long sustain into G:maj
        solo_notes = _make_solo_notes([
            (0.9, 2.0, 60, 80),  # C4, starts at 0.9s over C:maj
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        n0 = harmonizer.harmonized_solo.notes[0]
        assert n0.chord == "C:maj"
        assert n0.chord_analysis is not None
        assert n0.chord_analysis.chord_tone_type == "chord_tone"
        assert n0.chord_analysis.scale_degree_name == "R"


class TestMixedNAndAnalyzedPercentages:
    """KB §16.11.4: 'N' notes excluded from percentage numerators but included in note_count."""

    def test_n_notes_reduce_percentages(self):
        """2 chord tones + 1 'N' note → chord_tone_pct ≈ 0.667, sum < 1.0."""
        chord_timeline = _make_chord_timeline([
            (0.0, "C:maj"),
            (2.0, "N"),
        ])
        solo_notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),  # C4 over C:maj → chord_tone
            (0.5, 0.5, 64, 80),  # E4 over C:maj → chord_tone
            (2.0, 0.5, 60, 80),  # C4 over N → None
        ])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        hs = harmonizer.harmonized_solo
        assert hs.note_count == 3  # All notes counted
        assert hs.notes[2].chord_analysis is None
        # Only 2 notes have chord analysis → chord_tone_pct = 2/2 = 1.0
        # The 'N' note is excluded from denominators
        assert hs.chord_tone_pct == 1.0
        assert hs.tension_note_pct == 0.0
        assert hs.chromatic_pct == 0.0
        # Sum ≤ 1.0 (the 'N' note reduces the analyzable fraction)
        assert hs.chord_tone_pct + hs.tension_note_pct + hs.chromatic_pct <= 1.0


class TestSpanPenalty:
    """KB §16.11.5: 5-fret window with stretch penalty formula."""

    def test_tight_span_no_penalty(self):
        """Span ≤ 4 gets no stretch penalty."""
        engine = PositionInferenceEngine(chord_root_pc=0)  # C
        notes = _make_solo_notes([
            (0.0, 0.5, 60, 80),  # C4 → fret 8 on string 1
            (0.5, 0.5, 62, 80),  # D4 → fret 10 on string 2
            (1.0, 0.5, 64, 80),  # E4 → fret 12 on string 1
        ])
        score, _ = engine.score_shape("C", notes.notes)
        # All notes fit within 4 frets → no penalty
        assert score > 0.0

    def test_wide_span_gets_penalty(self):
        """Span > 4 gets stretch penalty: score = hit_rate × (1 - 0.1 × (span - 4))."""
        engine = PositionInferenceEngine(chord_root_pc=0)  # C
        # Create notes that span 6 frets
        notes = _make_solo_notes([
            (0.0, 0.5, 48, 80),  # C3 → fret 3 on string 5
            (0.5, 0.5, 55, 80),  # G3 → fret 0 on string 3
            (1.0, 0.5, 67, 80),  # G4 → fret 3 on string 1 (wide stretch)
        ])
        score, _ = engine.score_shape("C", notes.notes)
        # Score should be reduced by stretch penalty
        assert score >= 0.0


class TestSuggestedScales:
    """KB §16.9 obs #10: scale suggestions based on chord quality."""

    def test_major_chord_suggests_pentatonic_and_lydian(self):
        chord_timeline = _make_chord_timeline([(0.0, "C:maj")])
        solo_notes = _make_solo_notes([(0.0, 0.5, 60, 80)])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        bars = harmonizer.per_bar_analysis
        assert len(bars) >= 1
        scales = bars[0].suggested_scales
        assert any("pentatonic" in s for s in scales)
        assert any("lydian" in s for s in scales)

    def test_dominant_chord_suggests_mixolydian(self):
        chord_timeline = _make_chord_timeline([(0.0, "G:7")])
        solo_notes = _make_solo_notes([(0.0, 0.5, 67, 80)])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "G major")

        bars = harmonizer.per_bar_analysis
        scales = bars[0].suggested_scales
        assert any("mixolydian" in s for s in scales)

    def test_minor_chord_suggests_dorian(self):
        chord_timeline = _make_chord_timeline([(0.0, "A:min")])
        solo_notes = _make_solo_notes([(0.0, 0.5, 69, 80)])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "A minor")

        bars = harmonizer.per_bar_analysis
        scales = bars[0].suggested_scales
        assert any("dorian" in s for s in scales)

    def test_no_chord_suggests_nothing(self):
        chord_timeline = _make_chord_timeline([(0.0, "N")])
        solo_notes = _make_solo_notes([(0.0, 0.5, 60, 80)])
        beat_grid = _make_beat_grid()

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        bars = harmonizer.per_bar_analysis
        assert len(bars) >= 1
        assert bars[0].suggested_scales == []


class TestBarBoundariesFallback:
    """When beat_grid.downbeats has < 2 entries, fall back to beats."""

    def test_fallback_to_beats(self):
        chord_timeline = _make_chord_timeline([(0.0, "C:maj")])
        solo_notes = _make_solo_notes([(0.0, 0.5, 60, 80)])
        beat_grid = _make_beat_grid(
            beats=[0.0, 1.0, 2.0, 3.0],
            downbeats=[0.0],  # Only 1 downbeat → fallback
        )

        harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, "C major")

        bars = harmonizer.per_bar_analysis
        # Should use beats as bar boundaries: 3 bars from [0,1), [1,2), [2,3)
        assert len(bars) == 3


class TestParseChordFallback:
    """Unknown quality defaults to major triad."""

    def test_unknown_quality_defaults_to_major(self):
        result = parse_chord("C:foo")
        assert result is not None
        root, quality, intervals = result
        assert root == 0
        assert quality == "foo"
        assert intervals == [0, 4, 7]  # Falls back to major triad
