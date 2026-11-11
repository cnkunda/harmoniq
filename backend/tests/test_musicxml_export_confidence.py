"""W5: coarse confidence band metadata in MusicXML exports."""

from __future__ import annotations

import pytest

from app.exporter import export_musicxml_from_json
from app.musicxml_builder import build_musicxml
from app.schemas import BeatGrid, ChordEvent, ChordTimeline, SoloNotes, TimeSignature


def _beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
        beats=[0.0, 0.5, 1.0, 1.5],
        downbeats=[0.0],
    )


def _timeline() -> ChordTimeline:
    return ChordTimeline(
        events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.8)]
    )


def test_musicxml_carries_band_metadata_not_a_percentage():
    xml = build_musicxml(
        _beat_grid(),
        _timeline(),
        SoloNotes(notes=[]),
        title="W5",
        artist="Harmoniq",
        confidence_band="medium",
    )

    assert (
        '<miscellaneous-field name="harmoniq-confidence-band">medium'
        "</miscellaneous-field>" in xml
    )
    assert "%" not in xml


def test_musicxml_omits_band_metadata_when_unknown():
    xml = build_musicxml(
        _beat_grid(),
        _timeline(),
        SoloNotes(notes=[]),
        title="W5",
        artist="Harmoniq",
    )

    assert "harmoniq-confidence-band" not in xml


def test_musicxml_rejects_an_unknown_band():
    with pytest.raises(ValueError):
        build_musicxml(
            _beat_grid(),
            _timeline(),
            SoloNotes(notes=[]),
            confidence_band="certain",  # type: ignore[arg-type]
        )


def test_export_musicxml_from_json_carries_band():
    data, mime, ext, stem = export_musicxml_from_json(
        _beat_grid(),
        _timeline(),
        SoloNotes(notes=[]),
        title="W5",
        artist="Harmoniq",
        confidence_band="high",
    )

    text = data.decode("utf-8")
    assert mime.endswith("musicxml+xml")
    assert ext == ".musicxml"
    assert stem == "W5"
    assert ">high</miscellaneous-field>" in text
    assert "%" not in text
