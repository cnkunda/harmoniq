"""Tests for the W4 technique-label prototype."""

from __future__ import annotations

from app.fretting.techniques import label_techniques
from app.fretting.types import TabNote


def _note(
    pitch: int,
    onset: float,
    duration: float,
    string: int | None = None,
    fret: int | None = None,
) -> TabNote:
    return TabNote(
        pitch=pitch,
        onset=onset,
        offset=onset + duration,
        string=string,
        fret=fret,
    )


def _labels(notes: list[TabNote]) -> list[str]:
    return [
        tag
        for tags in label_techniques(notes, assignment=notes).by_index.values()
        for tag in tags
    ]


class TestLegato:
    def test_slide_on_tight_same_string_move(self) -> None:
        notes = [
            _note(64, 0.0, 0.2, string=1, fret=0),
            _note(66, 0.22, 0.2, string=1, fret=2),
        ]
        assert "slide" in _labels(notes)

    def test_hammer_on_ascending(self) -> None:
        notes = [
            _note(67, 0.0, 0.2, string=1, fret=3),
            _note(69, 0.24, 0.2, string=1, fret=5),
        ]
        assert "hammer_on" in _labels(notes)

    def test_pull_off_descending(self) -> None:
        notes = [
            _note(69, 0.0, 0.2, string=1, fret=5),
            _note(67, 0.24, 0.2, string=1, fret=3),
        ]
        assert "pull_off" in _labels(notes)

    def test_different_strings_are_not_legato(self) -> None:
        notes = [
            _note(64, 0.0, 0.2, string=1, fret=0),
            _note(65, 0.22, 0.2, string=2, fret=6),
        ]
        labels = _labels(notes)
        assert "slide" not in labels
        assert "hammer_on" not in labels


class TestVibrato:
    def test_repeated_notes(self) -> None:
        notes = [
            _note(64, 0.00, 0.05, string=1, fret=0),
            _note(64, 0.07, 0.05, string=1, fret=0),
            _note(64, 0.14, 0.05, string=1, fret=0),
            _note(64, 0.21, 0.05, string=1, fret=0),
        ]
        labels = label_techniques(notes, assignment=notes)
        assert labels.counts.get("vibrato") == 4


class TestWithoutAssignment:
    def test_only_vibrato_is_produced(self) -> None:
        notes = [
            _note(64, 0.00, 0.05),
            _note(64, 0.07, 0.05),
            _note(64, 0.14, 0.05),
        ]
        labels = label_techniques(notes)
        assert labels.counts == {"vibrato": 3}


class TestValidation:
    def test_misaligned_assignment(self) -> None:
        import pytest

        notes = [_note(64, 0.0, 0.2)]
        with pytest.raises(ValueError, match="align"):
            label_techniques(notes, assignment=[])
