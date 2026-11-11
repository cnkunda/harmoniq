"""Tests for W4 sequence-aware string/fret assignment."""

from __future__ import annotations

from app.fretting.assign import assign_tab, group_notes
from app.fretting.metrics import group_validity
from app.fretting.positions import Position
from app.fretting.tuning import drop_d, standard
from app.fretting.types import TabNote


def _note(pitch: int, onset: float, duration: float = 0.2) -> TabNote:
    return TabNote(pitch=pitch, onset=onset, offset=onset + duration)


class TestPitchAndAlignment:
    def test_pitch_is_preserved(self) -> None:
        notes = [_note(pitch, index * 0.2) for index, pitch in enumerate(
            [40, 43, 45, 47, 50, 52, 55]
        )]
        assignment = assign_tab(notes, mode="dp")
        assert [note.pitch for note in assignment.notes] == [
            note.pitch for note in notes
        ]
        assert all(
            note.string is not None and note.fret is not None
            for note in assignment.notes
        )
        assert assignment.total_cost >= 0.0

    def test_output_aligns_with_input_order(self) -> None:
        notes = [
            _note(67, onset=0.4),
            _note(64, onset=0.0),
            _note(65, onset=0.2),
        ]
        assignment = assign_tab(notes, mode="dp")
        assert [note.pitch for note in assignment.notes] == [67, 64, 65]

    def test_unassignable_pitch_is_reported(self) -> None:
        notes = [_note(30, 0.0), _note(64, 0.2)]
        assignment = assign_tab(notes, mode="dp")
        assert len(assignment.notes) == 2
        assert assignment.notes[0].string is None
        assert assignment.notes[1].string is not None
        assert len(assignment.unassignable) == 1


class TestBaseline:
    def test_baseline_per_note(self) -> None:
        notes = [_note(67, 0.0), _note(67, 0.2)]
        assignment = assign_tab(notes, mode="baseline")
        assert all(
            (note.string, note.fret) == (1, 3) for note in assignment.notes
        )


class TestPolyphony:
    def test_dp_uses_distinct_strings(self) -> None:
        notes = [_note(64, 0.0), _note(64, 0.0)]
        baseline = assign_tab(notes, mode="baseline")
        dp = assign_tab(notes, mode="dp")
        assert group_validity(baseline.groups) == 0.0
        assert group_validity(dp.groups) == 1.0
        strings = {note.string for note in dp.notes}
        assert len(strings) == 2

    def test_group_notes_tolerance(self) -> None:
        notes = [_note(64, 0.0), _note(67, 0.01), _note(69, 0.2)]
        groups = group_notes(notes, tolerance_s=0.03)
        assert [len(group) for group in groups] == [2, 1]


class TestWideVoicing:
    def test_relaxes_span_before_dropping_pitch(self) -> None:
        # E2 and E5 cannot share a <=5-fret hand frame on distinct strings,
        # so the strict pass finds nothing; the relaxed pass must still
        # assign both notes without losing pitch.
        notes = [_note(40, 0.0), _note(76, 0.0)]
        assignment = assign_tab(notes, mode="dp", max_span=5)
        assert not assignment.unassignable
        assert all(
            note.string is not None and note.fret is not None
            for note in assignment.notes
        )
        assert len({note.string for note in assignment.notes}) == 2


class TestTuningConditioning:
    def test_capo(self) -> None:
        tuning = standard(capo=3)
        assignment = assign_tab([_note(70, 0.0)], tuning=tuning, mode="dp")
        assert (assignment.notes[0].string, assignment.notes[0].fret) == (1, 3)

    def test_drop_d(self) -> None:
        assignment = assign_tab(
            [_note(38, 0.0)], tuning=drop_d(), mode="dp"
        )
        assert (assignment.notes[0].string, assignment.notes[0].fret) == (6, 0)


class TestDeterminism:
    def test_repeated_runs_match(self) -> None:
        notes = [
            _note(64, 0.0),
            _note(65, 0.2),
            _note(67, 0.4),
            _note(69, 0.6),
        ]
        first = assign_tab(notes, mode="dp")
        second = assign_tab(notes, mode="dp")
        assert [
            (note.string, note.fret) for note in first.notes
        ] == [(note.string, note.fret) for note in second.notes]

    def test_scale_stays_on_one_string(self) -> None:
        notes = [_note(pitch, index * 0.2) for index, pitch in enumerate(
            [64, 65, 67, 69, 71, 72]
        )]
        assignment = assign_tab(notes, mode="dp")
        assert [
            Position(note.string, note.fret) for note in assignment.notes
        ] == [
            Position(1, 0),
            Position(1, 1),
            Position(1, 3),
            Position(1, 5),
            Position(1, 7),
            Position(1, 8),
        ]


class TestValidation:
    def test_unknown_mode(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="mode"):
            assign_tab([_note(64, 0.0)], mode="magic")
