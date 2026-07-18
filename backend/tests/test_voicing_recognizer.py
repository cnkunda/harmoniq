"""Tests for Commit B9: MT3 Voicing Recognizer — CAGED shape detection."""
from __future__ import annotations

import pytest
from app.mt3.voicing_recognizer import (
    CAGED_SHAPES,
    VoicingResult,
    _midi_pitches_from_active_notes,
    _compute_expected_pitches,
    _compute_voicing_label,
    recognize_voicing,
)
from app.mt3.schemas import Mt3Event

_GUITAR_PROGRAM = 24


def _build_events_from_pitches(pitches: list[int]) -> dict[int, list[Mt3Event]]:
    """Build active_notes dict from MIDI pitches, grouped by pitch class."""
    active: dict[int, list[Mt3Event]] = {}
    for p in pitches:
        pc = p % 12
        event = Mt3Event(pitch=p, program=_GUITAR_PROGRAM, time=0.0, velocity=100, confidence=1.0, is_onset=True, is_offset=False)
        if pc not in active:
            active[pc] = []
        active[pc].append(event)
    return active


class TestVoicingRecognizer:

    def test_e_shape_open_e_major(self):
        """Open E major → E-shape, position 0."""
        # E-shape at position 0: expected MIDI pitches = [64, 59, 56, 52, 47, 40]
        active = _build_events_from_pitches([64, 59, 56, 52, 47, 40])
        result = recognize_voicing(active, "E", "maj")
        assert result.shape == "E", f"Expected E-shape, got {result.shape}"
        assert result.position == 0, f"Expected position 0, got {result.position}"
        assert result.confidence >= 0.6, f"Confidence {result.confidence} below threshold"

    def test_e_shape_barre_f_major(self):
        """Barre F major (fret 1) → E-shape, position 1."""
        # E-shape at position 1: [65, 60, 57, 53, 48, 41]
        active = _build_events_from_pitches([65, 60, 57, 53, 48, 41])
        result = recognize_voicing(active, "F", "maj")
        assert result.shape == "E", f"Expected E-shape, got {result.shape}"
        assert result.position == 1, f"Expected position 1, got {result.position}"
        assert result.confidence >= 0.6

    def test_e_shape_barre_g_major(self):
        """Barre G major (fret 3) → E-shape, position 3."""
        # E-shape at position 3: [67, 62, 59, 55, 50, 43]
        active = _build_events_from_pitches([67, 62, 59, 55, 50, 43])
        result = recognize_voicing(active, "G", "maj")
        assert result.shape == "E", f"Expected E-shape, got {result.shape}"
        assert result.position == 3, f"Expected position 3, got {result.position}"
        assert result.confidence >= 0.6

    def test_a_shape_open_a_major(self):
        """Open A major → A-shape, position 0."""
        # A-shape at position 0: [64, 61, 57, 52, 45]
        active = _build_events_from_pitches([64, 61, 57, 52, 45])
        result = recognize_voicing(active, "A", "maj")
        assert result.shape == "A", f"Expected A-shape, got {result.shape}"
        assert result.position == 0
        assert result.confidence >= 0.6

    def test_a_shape_barre_b_flat_major(self):
        """Barre Bb major (fret 1) → A-shape, position 1."""
        # A-shape at position 1: [65, 62, 58, 53, 46]
        active = _build_events_from_pitches([65, 62, 58, 53, 46])
        result = recognize_voicing(active, "Bb", "maj")
        assert result.shape == "A", f"Expected A-shape, got {result.shape}"
        assert result.position == 1
        assert result.confidence >= 0.6

    def test_c_shape_c_major_open(self):
        """Open C major → C-shape, position 0."""
        # C-shape at position 0: [64, 60, 55, 52, 48]
        active = _build_events_from_pitches([64, 60, 55, 52, 48])
        result = recognize_voicing(active, "C", "maj")
        assert result.shape == "C", f"Expected C-shape, got {result.shape}"
        assert result.position == 0
        assert result.confidence >= 0.6

    def test_d_shape_d_major_open(self):
        """Open D major → D-shape, position 0."""
        # D-shape at position 0: [66, 62, 57, 50]
        active = _build_events_from_pitches([66, 62, 57, 50])
        result = recognize_voicing(active, "D", "maj")
        assert result.shape == "D", f"Expected D-shape, got {result.shape}"
        assert result.position == 0
        assert result.confidence >= 0.6

    def test_g_shape_g_major_open(self):
        """Open G major → G-shape, position 0."""
        # G-shape at position 0: [67, 62, 55, 50, 47, 43]
        active = _build_events_from_pitches([67, 62, 55, 50, 47, 43])
        result = recognize_voicing(active, "G", "maj")
        assert result.shape == "G", f"Expected G-shape, got {result.shape}"
        assert result.position == 0
        assert result.confidence >= 0.6

    def test_unknown_voicing_no_match(self):
        """Random pitch set with no clear CAGED shape → None."""
        active = _build_events_from_pitches([40, 44, 48, 52, 56, 60])
        result = recognize_voicing(active, "C", "dim")
        assert result.shape is None
        assert result.position is None

    def test_empty_events_returns_none(self):
        """Empty active_notes → None."""
        result = recognize_voicing({}, "C", "maj")
        assert result.shape is None
        assert result.position is None

    def test_single_note_returns_none(self):
        """Single active pitch → None (need ≥3 for chord)."""
        active = _build_events_from_pitches([60])
        result = recognize_voicing(active, "C", "maj")
        assert result.shape is None

    def test_two_notes_returns_none(self):
        """Two active pitches → None (need ≥3 for chord)."""
        active = _build_events_from_pitches([60, 64])
        result = recognize_voicing(active, "C", "maj")
        assert result.shape is None

    def test_voicing_label_open(self):
        """_compute_voicing_label for open position."""
        label = _compute_voicing_label("E", 0)
        assert "E-shape" in label and "open" in label

    def test_voicing_label_barre(self):
        """_compute_voicing_label for barre position."""
        label = _compute_voicing_label("A", 5)
        assert "A-shape" in label and "V" in label

    def test_voicing_label_none(self):
        """_compute_voicing_label for None shape."""
        assert _compute_voicing_label(None, None) == ""

    def test_compute_expected_pitches_e_shape(self):
        """_compute_expected_pitches returns correct MIDI pitches for E-shape at position 0."""
        pitches = _compute_expected_pitches("E", 0)
        assert pitches == {40, 47, 52, 56, 59, 64}

    def test_compute_expected_pitches_a_shape(self):
        """_compute_expected_pitches returns correct MIDI pitches for A-shape at position 0."""
        pitches = _compute_expected_pitches("A", 0)
        assert pitches == {45, 52, 57, 61, 64}

    def test_compute_expected_pitches_c_shape(self):
        """_compute_expected_pitches returns correct MIDI pitches for C-shape at position 0."""
        pitches = _compute_expected_pitches("C", 0)
        assert pitches == {48, 52, 55, 60, 64}

    def test_midi_pitches_from_active_notes(self):
        """_midi_pitches_from_active_notes collects unique pitches."""
        active = _build_events_from_pitches([40, 40, 47, 52, 56])
        result = _midi_pitches_from_active_notes(active)
        assert result == {40, 47, 52, 56}
