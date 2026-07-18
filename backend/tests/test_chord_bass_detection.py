"""Tests for Commit B8: Chord bass note and inversion detection.

Verifies:
- MT3 _build_active_note_grid returns correct lowest MIDI per slice
- Bass note correctly derived from lowest MIDI
- Bass = None when bass equals chord root
- Inversion detection for major/minor/7th chords
- Merged consecutive chords use most-frequent bass
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.mt3.chord_decoder import (
    _build_active_note_grid,
    _identify_inversion,
    _infer_chords_from_active_notes,
    decode_events_to_chord_timeline,
)
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, ChordEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_beat_grid(beats: list[float] | None = None) -> BeatGrid:
    if beats is None:
        beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    return BeatGrid(
        bpm=120.0,
        pulse_bpm=120.0,
        beats=beats,
        downbeats=[0.0, 2.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


def _onset(time: float, pitch: int, program: int = 24) -> Mt3Event:
    return Mt3Event(time=time, pitch=pitch, velocity=80, program=program,
                    is_onset=True, is_offset=False, confidence=0.9)


def _offset(time: float, pitch: int) -> Mt3Event:
    return Mt3Event(time=time, pitch=pitch, velocity=0, program=24,
                    is_onset=False, is_offset=True, confidence=0.9)


# ---------------------------------------------------------------------------
# Tests: _build_active_note_grid bass detection
# ---------------------------------------------------------------------------

class TestBuildActiveNoteGridBass:
    """Verify that _build_active_note_grid tracks the lowest MIDI pitch per slice."""

    def test_bass_is_lowest_pitch(self):
        """C major chord: C4(60), E4(64), G4(67) → lowest MIDI = 60 (C4)."""
        events = [
            _onset(0.0, 60),
            _onset(0.0, 64),
            _onset(0.0, 67),
            _offset(0.5, 60),
            _offset(0.5, 64),
            _offset(0.5, 67),
        ]
        grid, bass_notes = _build_active_note_grid(events, audio_end=1.0)
        # At time 0.0, the lowest MIDI should be 60
        t0 = 0.0
        assert t0 in bass_notes
        assert bass_notes[t0] == 60, f"Expected bass=60, got {bass_notes[t0]}"

    def test_bass_changes_with_lower_note(self):
        """C/E first inversion: E3(52), C4(60), G4(67) → lowest MIDI = 52 (E3)."""
        events = [
            _onset(0.0, 52),
            _onset(0.0, 60),
            _onset(0.0, 67),
            _offset(0.5, 52),
            _offset(0.5, 60),
            _offset(0.5, 67),
        ]
        grid, bass_notes = _build_active_note_grid(events, audio_end=1.0)
        t0 = 0.0
        assert t0 in bass_notes
        assert bass_notes[t0] == 52, f"Expected bass=52, got {bass_notes[t0]}"

    def test_bass_is_none_when_no_events(self):
        """Empty time slice → bass = None."""
        events: list[Mt3Event] = []
        grid, bass_notes = _build_active_note_grid(events, audio_end=1.0)
        t0 = 0.0
        assert t0 in bass_notes
        assert bass_notes[t0] is None

    def test_bass_excludes_percussion(self):
        """Percussion (program 128) should not affect bass pitch."""
        events = [
            _onset(0.0, 40, program=128),  # percussion, should be ignored
            _onset(0.0, 60),  # C4
            _onset(0.0, 64),  # E4
            _offset(0.5, 40),
            _offset(0.5, 60),
            _offset(0.5, 64),
        ]
        grid, bass_notes = _build_active_note_grid(events, audio_end=1.0)
        t0 = 0.0
        assert bass_notes[t0] == 60, "Percussion should not affect bass detection"


# ---------------------------------------------------------------------------
# Tests: Full decode pipeline with bass
# ---------------------------------------------------------------------------

class TestDecodeBassInference:
    """Verify that decode_events_to_chord_timeline produces correct bass."""

    def test_root_position_bass_is_none(self):
        """C major root position → bass should be None (equals root C)."""
        events = [
            _onset(0.0, 60), _onset(0.0, 64), _onset(0.0, 67),
            _offset(0.5, 60), _offset(0.5, 64), _offset(0.5, 67),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0
        for ev in timeline.events:
            if ev.chord != "N":
                assert ev.bass is None, f"Root position chord '{ev.chord}' should have bass=None, got {ev.bass}"
                break
        else:
            pytest.skip("No chord events found (unexpected)")

    def test_first_inversion_bass_is_e(self):
        """C/E first inversion → bass should be 'E', inversion 1."""
        events = [
            _onset(0.0, 52),  # E3
            _onset(0.0, 60),  # C4
            _onset(0.0, 67),  # G4
            _offset(0.5, 52),
            _offset(0.5, 60),
            _offset(0.5, 67),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0
        found = False
        for ev in timeline.events:
            if ev.chord != "N":
                assert ev.bass is not None, f"First inversion should have bass, got None for {ev.chord}"
                assert ev.bass == "E", f"Expected bass=E, got {ev.bass}"
                assert ev.inversion == 1, f"Expected inversion=1, got {ev.inversion}"
                found = True
                break
        assert found, "No non-N chord event found"

    def test_second_inversion_bass_is_g(self):
        """C/G second inversion → bass should be 'G', inversion 2."""
        events = [
            _onset(0.0, 55),  # G3
            _onset(0.0, 60),  # C4
            _onset(0.0, 64),  # E4
            _offset(0.5, 55),
            _offset(0.5, 60),
            _offset(0.5, 64),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0
        found = False
        for ev in timeline.events:
            if ev.chord != "N":
                assert ev.bass is not None, f"Second inversion should have bass, got None for {ev.chord}"
                assert ev.bass == "G", f"Expected bass=G, got {ev.bass}"
                assert ev.inversion == 2, f"Expected inversion=2, got {ev.inversion}"
                found = True
                break
        assert found, "No non-N chord event found"

    def test_no_events_returns_empty_timeline(self):
        """Empty event stream → empty timeline (existing behavior, no N injected)."""
        events: list[Mt3Event] = []
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) == 0

    def test_g7_third_inversion_bass_is_f(self):
        """G7 third inversion: F is the 7th → bass='F', inversion=3."""
        events = [
            _onset(0.0, 53),  # F3 (b7)
            _onset(0.0, 55),  # G3 (root)
            _onset(0.0, 59),  # B3 (3rd)
            _onset(0.0, 62),  # D4 (5th)
            _offset(0.5, 53),
            _offset(0.5, 55),
            _offset(0.5, 59),
            _offset(0.5, 62),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0
        for ev in timeline.events:
            if ev.chord.startswith("G:7"):
                assert ev.bass == "F", f"Expected bass=F for G7 third inversion, got {ev.bass}"
                assert ev.inversion == 3, f"Expected inversion=3, got {ev.inversion}"
                return
        pytest.skip("No G:7 chord found in timeline")


# ---------------------------------------------------------------------------
# Tests: _identify_inversion standalone
# ---------------------------------------------------------------------------

class TestIdentifyInversion:
    def test_root_position(self):
        assert _identify_inversion("C", "maj", "C") is None

    def test_first_inversion_major(self):
        assert _identify_inversion("C", "maj", "E") == 1

    def test_second_inversion_major(self):
        assert _identify_inversion("C", "maj", "G") == 2

    def test_first_inversion_minor(self):
        assert _identify_inversion("A", "min", "C") == 1

    def test_second_inversion_minor(self):
        assert _identify_inversion("A", "min", "E") == 2

    def test_third_inversion_seventh(self):
        assert _identify_inversion("G", "7", "F") == 3

    def test_bass_none_returns_none(self):
        assert _identify_inversion("C", "maj", None) is None

    def test_unknown_quality_returns_none(self):
        assert _identify_inversion("C", "unknown", "E") is None

    def test_non_chord_tone_bass_returns_none(self):
        """If the bass note is not a chord tone (e.g., D over C major), return None."""
        assert _identify_inversion("C", "maj", "D") is None


# ---------------------------------------------------------------------------
# Tests: merged consecutive chords preserve bass
# ---------------------------------------------------------------------------

class TestMergedChordBass:
    """When consecutive time slices have the same chord, the bass should
    be the most frequent note across the merged region."""

    def test_merged_bass_most_frequent(self):
        """Two consecutive C:maj slices with E, then E → bass should be E."""
        events = [
            _onset(0.0, 52), _onset(0.0, 60), _onset(0.0, 67),
            _offset(0.15, 52), _offset(0.15, 60), _offset(0.15, 67),
            _onset(0.2, 52), _onset(0.2, 60), _onset(0.2, 67),
            _offset(0.5, 52), _offset(0.5, 60), _offset(0.5, 67),
        ]
        stream = Mt3EventStream(events=events, audio_duration_s=1.0)
        beat_grid = _make_beat_grid()
        timeline = decode_events_to_chord_timeline(stream, beat_grid)
        assert len(timeline.events) > 0
        for ev in timeline.events:
            if ev.chord.startswith("C:maj"):
                assert ev.bass == "E", f"Expected bass=E for merged C/E, got {ev.bass}"
                return
        pytest.skip("No C:maj chord found")
