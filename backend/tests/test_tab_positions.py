"""Tests for F2: primary and alternate guitar-position maps."""
from __future__ import annotations

from app.pipeline_proof import NoteEvent
from app.tab_positions import alternate_positions, chosen_beat_notes, primary_positions

OPEN_BY_STRING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}


def _events(*pitches: int, bpm: float = 120.0) -> list[NoteEvent]:
    seconds_per_beat = 60.0 / bpm
    return [
        NoteEvent(
            start_s=index * seconds_per_beat,
            end_s=index * seconds_per_beat + 0.2,
            pitch_midi=pitch,
            amplitude=1.0,
        )
        for index, pitch in enumerate(pitches)
    ]


class TestChosenBeatNotes:
    def test_keeps_strongest_pitch_per_slot(self) -> None:
        bpm = 120.0
        events = [
            NoteEvent(start_s=0.0, end_s=0.2, pitch_midi=64, amplitude=0.4),
            NoteEvent(start_s=0.01, end_s=0.2, pitch_midi=67, amplitude=0.9),
        ]
        chosen = chosen_beat_notes(events, bpm=bpm)
        assert list(chosen.values())[0].pitch_midi == 67


class TestPrimaryPositions:
    def test_positions_preserve_pitch(self) -> None:
        chosen = chosen_beat_notes(_events(64, 67, 69), bpm=120.0)
        positions = primary_positions(chosen)
        assert len(positions) == 3
        for (_slot, pitch), (string, fret) in positions.items():
            assert OPEN_BY_STRING[string] + fret == pitch


class TestAlternatePositions:
    def test_alternate_is_a_different_fingering(self) -> None:
        chosen = chosen_beat_notes(_events(64, 67, 69), bpm=120.0)
        primary = primary_positions(chosen)
        alt = alternate_positions(chosen)
        assert alt is not None
        assert alt != primary
        for (_slot, pitch), (string, fret) in alt.items():
            assert OPEN_BY_STRING[string] + fret == pitch

    def test_alternate_prefers_mid_neck_when_available(self) -> None:
        chosen = chosen_beat_notes(_events(64), bpm=120.0)
        alt = alternate_positions(chosen)
        assert alt is not None
        (_slot, _pitch), (_string, fret) = next(iter(alt.items()))
        assert 5 <= fret <= 12

    def test_returns_none_when_only_one_position_exists(self) -> None:
        # Pitch 40 is the open low E — only playable on string 6 fret 0.
        chosen = chosen_beat_notes(_events(40), bpm=120.0)
        assert alternate_positions(chosen) is None

    def test_empty_input_returns_none(self) -> None:
        assert alternate_positions({}) is None
