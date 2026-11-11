"""Tests for T3 per-note lead/rhythm roles."""
from __future__ import annotations

from app.part_role import assign_solo_note_part_roles, dominant_part_role
from app.schemas import SoloNote, SoloNotes


def _note(start: float, duration: float, pitch: int = 64) -> SoloNote:
    return SoloNote(start_time=start, duration=duration, pitch=pitch, velocity=90)


class TestAssignSoloNotePartRoles:
    def test_long_single_line_notes_are_lead(self) -> None:
        notes = SoloNotes(notes=[_note(0.0, 0.6, 64), _note(0.8, 0.5, 67)])
        stats = assign_solo_note_part_roles(notes)
        assert stats.lead == 2
        assert stats.rhythm == 0
        assert all(note.part_role == "lead" for note in notes.notes)

    def test_simultaneous_attacks_are_rhythm(self) -> None:
        notes = SoloNotes(
            notes=[_note(0.0, 0.4, 60), _note(0.01, 0.4, 64), _note(0.02, 0.4, 67)]
        )
        stats = assign_solo_note_part_roles(notes)
        assert stats.rhythm == 3
        assert dominant_part_role(stats) == "rhythm"

    def test_short_note_on_chord_change_is_rhythm(self) -> None:
        notes = SoloNotes(notes=[_note(1.0, 0.1, 60), _note(2.5, 0.5, 67)])
        stats = assign_solo_note_part_roles(notes, chord_timestamps=[1.0, 2.0])
        assert notes.notes[0].part_role == "rhythm"
        assert notes.notes[1].part_role == "lead"
        assert dominant_part_role(stats) == "mixed"

    def test_empty_notes(self) -> None:
        stats = assign_solo_note_part_roles(SoloNotes(notes=[]))
        assert stats.total == 0
        assert dominant_part_role(stats) is None
