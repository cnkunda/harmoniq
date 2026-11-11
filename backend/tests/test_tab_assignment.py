"""Tests for F1: persisted tab positions on solo notes."""
from __future__ import annotations

import pytest

from app.schemas import SoloNote, SoloNotes
from app.tab_assignment import assign_solo_note_positions


def _notes(*pitches: int) -> SoloNotes:
    return SoloNotes(
        notes=[
            SoloNote(
                start_time=float(i) * 0.5,
                duration=0.4,
                pitch=pitch,
                velocity=80,
            )
            for i, pitch in enumerate(pitches)
        ]
    )


class TestAssignSoloNotePositions:
    def test_assigns_positions_for_playable_notes(self) -> None:
        notes = _notes(64, 67, 69)
        assigned = assign_solo_note_positions(notes)
        assert assigned == 3
        assert all(note.string is not None and note.fret is not None for note in notes.notes)

    def test_positions_preserve_pitch(self) -> None:
        notes = _notes(64, 67, 69)
        assign_solo_note_positions(notes)
        open_by_string = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
        for note in notes.notes:
            assert open_by_string[note.string] + note.fret == note.pitch

    def test_unplayable_pitch_is_left_unassigned(self) -> None:
        notes = _notes(64, 10)
        assigned = assign_solo_note_positions(notes)
        assert assigned == 1
        assert notes.notes[1].string is None
        assert notes.notes[1].fret is None

    def test_baseline_mode_env(self, monkeypatch) -> None:
        monkeypatch.setenv("HARMONIQ_TAB_ASSIGNMENT_MODE", "baseline")
        notes = _notes(64)
        assert assign_solo_note_positions(notes) == 1
        assert (notes.notes[0].string, notes.notes[0].fret) == (1, 0)

    def test_skip_env_leaves_positions_untouched(self, monkeypatch) -> None:
        monkeypatch.setenv("HARMONIQ_SKIP_TAB_ASSIGNMENT", "1")
        notes = _notes(64)
        assert assign_solo_note_positions(notes) == 0
        assert notes.notes[0].string is None

    def test_empty_notes_returns_zero(self) -> None:
        assert assign_solo_note_positions(SoloNotes(notes=[])) == 0
