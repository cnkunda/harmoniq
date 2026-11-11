"""Tests for the string-aware W4 ground-truth loaders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.tab_ground_truth import (
    TabGroundTruthError,
    load_egset12_tab,
    load_guitar_techs_tab,
    load_guitarset_tab,
    load_tab_ground_truth,
)


def _write_jams(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _jams(annotations: list[dict]) -> dict:
    return {"annotations": annotations}


class TestStringAwareJams:
    def test_data_source_maps_to_string(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "track.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": "0"},
                        "data": [
                            {"time": 0.0, "duration": 0.5, "value": 40.2}
                        ],
                    },
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": "5"},
                        "data": [
                            {"time": 0.6, "duration": 0.5, "value": 64.4}
                        ],
                    },
                ]
            ),
        )
        notes = load_guitarset_tab(path)
        assert len(notes) == 2
        # data_source 0 = low E (string 6); 5 = high E (string 1).
        assert (notes[0].string, notes[0].fret) == (6, 0)
        assert (notes[1].string, notes[1].fret) == (1, 0)
        assert notes[0].pitch == 40
        assert notes[1].pitch == 64

    def test_egset12_loader(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "01.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": 1},
                        "data": [{"time": 0.0, "duration": 0.2, "value": 50}],
                    }
                ]
            ),
        )
        notes = load_egset12_tab(path)
        assert (notes[0].string, notes[0].fret) == (5, 5)

    def test_invalid_data_source(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "bad.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": 9},
                        "data": [{"time": 0.0, "duration": 0.2, "value": 64}],
                    }
                ]
            ),
        )
        with pytest.raises(TabGroundTruthError, match="data_source"):
            load_guitarset_tab(path)

    def test_missing_data_source(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "missing.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {},
                        "data": [{"time": 0.0, "duration": 0.2, "value": 64}],
                    }
                ]
            ),
        )
        with pytest.raises(TabGroundTruthError, match="data_source"):
            load_guitarset_tab(path)

    def test_out_of_range_fret(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "low.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": 0},
                        "data": [{"time": 0.0, "duration": 0.2, "value": 39}],
                    }
                ]
            ),
        )
        with pytest.raises(TabGroundTruthError, match="outside"):
            load_guitarset_tab(path)

    def test_no_note_midi(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "chords.jams",
            _jams([{"namespace": "chord", "data": []}]),
        )
        with pytest.raises(TabGroundTruthError, match="no note_midi"):
            load_guitarset_tab(path)


class TestGuitarTechs:
    def _write_midi(self, path: Path) -> None:
        import pretty_midi

        midi = pretty_midi.PrettyMIDI()
        for name, pitch in zip(
            ["e", "B", "G", "D", "A", "E"], [64, 59, 55, 50, 45, 40]
        ):
            instrument = pretty_midi.Instrument(program=0, name=name)
            instrument.notes.append(
                pretty_midi.Note(
                    velocity=80, pitch=pitch, start=0.0, end=0.5
                )
            )
            midi.instruments.append(instrument)
        midi.write(str(path))

    def test_loads_per_string_midi(self, tmp_path: Path) -> None:
        path = tmp_path / "track.mid"
        self._write_midi(path)
        notes = load_guitar_techs_tab(path)
        assert len(notes) == 6
        assert {
            (note.string, note.fret) for note in notes
        } == {(string, 0) for string in range(1, 7)}

    def test_rejects_missing_string_tracks(self, tmp_path: Path) -> None:
        import pretty_midi

        path = tmp_path / "partial.mid"
        midi = pretty_midi.PrettyMIDI()
        for name, pitch in [("e", 64), ("B", 59), ("G", 55)]:
            instrument = pretty_midi.Instrument(program=0, name=name)
            instrument.notes.append(
                pretty_midi.Note(
                    velocity=80, pitch=pitch, start=0.0, end=0.5
                )
            )
            midi.instruments.append(instrument)
        midi.write(str(path))
        with pytest.raises(TabGroundTruthError, match="six named string"):
            load_guitar_techs_tab(path)


class TestDispatcher:
    def test_unknown_format(self, tmp_path: Path) -> None:
        with pytest.raises(TabGroundTruthError, match="does not carry"):
            load_tab_ground_truth(tmp_path / "x", gt_format="midi")

    def test_guitarset_dispatch(self, tmp_path: Path) -> None:
        path = _write_jams(
            tmp_path / "track.jams",
            _jams(
                [
                    {
                        "namespace": "note_midi",
                        "annotation_metadata": {"data_source": 5},
                        "data": [{"time": 0.0, "duration": 0.2, "value": 64}],
                    }
                ]
            ),
        )
        notes = load_tab_ground_truth(path, gt_format="guitarset_jams")
        assert notes[0].string == 1
