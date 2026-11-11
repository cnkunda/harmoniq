"""Tests for F3 rhythm charts and lead+rhythm merging."""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES
from app.pipeline_proof import NoteEvent, build_gp5_from_note_events
from app.tab_rhythm import (
    build_rhythm_gp5_base64,
    chord_positions,
    merge_rhythm_into_gp5,
)

gp = pytest.importorskip("guitarpro")

OPEN_BY_STRING = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}


def _pitch_classes(chord: str) -> set[int]:
    root, quality = chord.split(":")
    root_pc = ROOT_NOTES.index(root)
    return {(root_pc + interval) % 12 for interval in CHORD_INTERVALS[quality]}


def _parse_base64(b64: str) -> "gp.Song":
    raw = base64.b64decode(b64)
    return _parse_bytes(raw)


def _parse_bytes(raw: bytes) -> "gp.Song":
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "chart.gp5"
        path.write_bytes(raw)
        return gp.parse(str(path))


def _notes_for_track(song: "gp.Song", track_index: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for measure in song.tracks[track_index].measures:
        for beat in measure.voices[0].beats:
            for note in beat.notes:
                out.append((int(note.string), int(note.value)))
    return out


class TestChordPositions:
    def test_voicing_matches_chord_pitch_classes(self) -> None:
        positions = chord_positions("C:maj")
        assert len(positions) == 3
        assert len({p.string for p in positions}) == 3
        actual = {(OPEN_BY_STRING[p.string] + p.fret) % 12 for p in positions}
        assert actual == _pitch_classes("C:maj")

    def test_unknown_or_no_chord_returns_empty(self) -> None:
        assert chord_positions("N") == []
        assert chord_positions("H:maj") == []


class TestRhythmChart:
    def test_builds_parseable_strum_chart(self) -> None:
        b64 = build_rhythm_gp5_base64([(0.0, "C:maj"), (2.0, "G:maj")], bpm=120.0)
        song = _parse_base64(b64)
        assert song.tracks[0].name == "Rhythm"
        notes = _notes_for_track(song, 0)
        assert notes

    def test_merge_adds_second_track_with_rhythm_notes(self) -> None:
        lead_events = [
            NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0),
            NoteEvent(start_s=0.5, end_s=0.75, pitch_midi=67, amplitude=1.0),
        ]
        with tempfile.TemporaryDirectory() as td:
            lead_path = Path(td) / "lead.gp5"
            build_gp5_from_note_events(lead_events, bpm=120.0, output_gp5=lead_path, title="Test")
            merged = merge_rhythm_into_gp5(
                lead_path.read_bytes(),
                [(0.0, "C:maj")],
                bpm=120.0,
            )
        song = _parse_bytes(merged)
        assert len(song.tracks) == 2
        assert song.tracks[0].name == "Guitar"
        assert song.tracks[1].name == "Rhythm"
        assert _notes_for_track(song, 0)
        assert _notes_for_track(song, 1)

    def test_merge_handles_no_chords(self) -> None:
        lead_events = [NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0)]
        with tempfile.TemporaryDirectory() as td:
            lead_path = Path(td) / "lead.gp5"
            build_gp5_from_note_events(lead_events, bpm=120.0, output_gp5=lead_path)
            merged = merge_rhythm_into_gp5(lead_path.read_bytes(), [], bpm=120.0)
        song = _parse_bytes(merged)
        assert len(song.tracks) == 2
        assert _notes_for_track(song, 1) == []
