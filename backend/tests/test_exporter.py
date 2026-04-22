from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_export_gp5_too_small_422() -> None:
    tiny = base64.b64encode(b"x" * 16).decode("ascii")
    r = client.post("/export", json={"gp5_base64": tiny, "format": "midi"})
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


def test_export_invalid_base64_422() -> None:
    r = client.post(
        "/export",
        json={"gp5_base64": "not-valid-base64!!!", "format": "midi"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]


def test_export_pdf_unsupported_422() -> None:
    ok_size = base64.b64encode(b"x" * 64).decode("ascii")
    r = client.post("/export", json={"gp5_base64": ok_size, "format": "pdf"})
    assert r.status_code == 422
    assert "PDF" in r.json()["detail"] or "not available" in r.json()["detail"].lower()


def test_export_disabled_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_EXPORT", "1")
    ok_size = base64.b64encode(b"x" * 64).decode("ascii")
    r = client.post("/export", json={"gp5_base64": ok_size, "format": "midi"})
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"].lower()


# --- New MusicXML Generation Tests ---

def test_export_musicxml_from_json_basic():
    from app.schemas import BeatGrid, ChordTimeline, SoloNotes, TimeSignature, ChordEvent, SoloNote
    from app.exporter import export_musicxml_from_json
    import music21 # Will need to import music21 for parsing and assertions

    # 1. Create mock data
    # A simple 4/4 measure at 120 BPM, with a C major chord and a C4 note
    beat_grid = BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5], # quarter notes
        downbeats=[0.0, 2.0], # Two downbeats to create at least one measure boundary
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
    )
    chord_timeline = ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ]
    )
    solo_notes = SoloNotes(
        notes=[
            SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100), # C4 for a quarter note
        ]
    )

    # 2. Call the function
    data, media_type, file_extension, stem = export_musicxml_from_json(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        title="Test Score",
        artist="Test Artist",
        key_signature="C major",
    )

    # 3. Assert on basic return values
    assert media_type == "application/vnd.recordare.musicxml+xml"
    assert file_extension == ".musicxml"
    assert "test_score" in stem.lower()
    assert isinstance(data, bytes)
    musicxml_str = data.decode("utf-8")

    # 4. Parse MusicXML with music21 and assert on content
    score = music21.converter.parse(musicxml_str)

    # Check basic score structure
    assert len(score.parts) == 1
    part = score.parts[0]
    assert part.partName == "Lead Sheet"

    # Check measures
    measures = list(part.getElementsByClass('Measure'))
    assert len(measures) >= 1 # At least one measure should be created

    # Check first measure for attributes
    first_measure = measures[0]
    assert first_measure.number == 1

    # Check Time Signature
    ts = first_measure.getTimeSignatures()[0]
    assert ts.numerator == 4
    assert ts.denominator == 4

    # Check Key Signature
    ks = first_measure.getKeySignatures()[0]
    assert ks.mode == "major"
    assert ks.tonic.name == "C"

    # Check Tempo
    tempo = first_measure.getElementsByClass(music21.tempo.MetronomeMark)[0]
    assert tempo.number == 120

    # Check Chord Symbol
    harmony = first_measure.getElementsByClass(music21.harmony.ChordSymbol)[0]
    assert harmony.root().name == "C"
    assert harmony.quality == "major"

    # Check Note
    note = first_measure.getElementsByClass(music21.note.Note)[0]
    assert note.nameWithOctave == "C4"
    assert note.duration.quarterLength == 1.0 # A quarter note
