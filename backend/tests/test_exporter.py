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
    ks = first_measure.keySignature
    assert ks is not None
    assert ks.sharps == 0

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


# --- Commit 106: Solo Rhythm Quantization & Measure-Level Sanity ---


def _build_musicxml(notes, key="C major", downbeats=None, tick_value=0.25):
    from app.schemas import BeatGrid, ChordTimeline, SoloNotes, TimeSignature, ChordEvent, SoloNote
    from app.exporter import export_musicxml_from_json

    beat_grid = BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5],
        downbeats=downbeats or [0.0, 2.0],
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=tick_value,
    )
    chord_timeline = ChordTimeline(
        events=[ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
    )
    solo_notes = SoloNotes(
        notes=[SoloNote(start_time=s, duration=d, pitch=p, velocity=v) for s, d, p, v in notes]
    )
    data, _, _, _ = export_musicxml_from_json(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        title="Rhythm Test",
        artist="Test Artist",
        key_signature=key,
    )
    return data.decode("utf-8"), solo_notes


def test_export_musicxml_16th_and_dotted_types():
    """16th notes render as <type>16th</type>; dotted quarter (3/2 ql) and
    dotted eighth (3/4 ql) both carry exactly one <dot>."""
    import music21

    notes = [
        (0.0, 0.125, 60, 100),   # 16th
        (0.25, 0.75, 62, 100),   # dotted quarter = 3/2 ql
        (1.0, 0.375, 64, 100),   # dotted eighth = 3/4 ql
    ]
    xml, _ = _build_musicxml(notes)

    score = music21.converter.parse(xml)
    notes_out = [n for n in score.flatten().notes if n.isNote]
    assert [n.duration.type for n in notes_out] == ["16th", "quarter", "eighth"]
    assert [n.duration.dots for n in notes_out] == [0, 1, 1]
    # Exactly one 16th rest fills the 0.125s gap
    rests = [e for e in score.flatten().notesAndRests if e.isRest]
    assert any(r.duration.type == "16th" for r in rests)


def test_export_musicxml_triplet_rhythm():
    """A triplet eighth (1/3 quarter) survives quantization as a 3-in-2 tuplet."""
    import music21

    notes = [
        (0.0, 1 / 6, 60, 100),
        (1 / 6, 1 / 6, 62, 100),
        (1 / 3, 1 / 6, 64, 100),
    ]
    xml, _ = _build_musicxml(notes)

    score = music21.converter.parse(xml)
    notes_out = [n for n in score.flatten().notes if n.isNote]
    assert len(notes_out) == 3
    for n in notes_out:
        assert n.duration.type == "eighth"
        assert n.duration.quarterLength == pytest.approx(1 / 3, abs=1e-3)
        assert len(n.duration.tuplets) == 1
        assert n.duration.tuplets[0].numberNotesActual == 3
        assert n.duration.tuplets[0].numberNotesNormal == 2


def test_export_musicxml_divisions_on_lcm_grid():
    """Divisions stay a multiple of 480 and every measure carries <attributes>."""
    import re

    notes = [
        (0.0, 0.125, 60, 100),   # 16th
        (0.25, 1 / 6, 62, 100),  # triplet eighth
        (0.5, 0.5, 64, 100),
    ]
    xml, _ = _build_musicxml(notes)

    divs = [int(x) for x in re.findall(r"<divisions>(\d+)</divisions>", xml)]
    assert divs
    assert all(d % 480 == 0 for d in divs)

    measure_blocks = re.findall(r"<measure\b[^>]*>(.*?)</measure>", xml, re.DOTALL)
    assert measure_blocks
    assert all("<attributes>" in block for block in measure_blocks)


def test_export_musicxml_tied_note_across_measures():
    """A note spanning the barline becomes tied segments with merged <notations>."""
    import re

    notes = [(1.5, 2.0, 60, 90)]  # starts halfway through measure 1, spans into 2
    xml, _ = _build_musicxml(notes, downbeats=[0.0, 2.0, 4.0])

    note_blocks = re.findall(r"<note\b[^>]*>.*?</note>", xml, re.DOTALL)
    tied_blocks = [b for b in note_blocks if "<tied" in b]
    assert len(tied_blocks) == 2
    for block in tied_blocks:
        # Exactly one <notations> carrying both <tied> and <technical> —
        # a duplicate <notations> would break AlphaTab rendering.
        assert block.count("<notations>") == 1
        assert "<tied" in block
        assert "<technical>" in block
        assert "<string>" in block and "<fret>" in block


def test_export_musicxml_quintuplet_rhythm():
    """On a 1/5-tick grid, a 4/5 ql duration renders as a 5-in-4 tuplet."""
    import music21

    notes = [
        (0.0, 0.4, 60, 100),   # 4/5 quarter = quintuplet quarter
    ]
    xml, _ = _build_musicxml(notes, tick_value=0.2)

    score = music21.converter.parse(xml)
    notes_out = [n for n in score.flatten().notes if n.isNote]
    assert len(notes_out) == 1
    n = notes_out[0]
    assert n.duration.quarterLength == pytest.approx(4 / 5, abs=1e-3)
    assert len(n.duration.tuplets) == 1
    assert n.duration.tuplets[0].numberNotesActual == 5
    assert n.duration.tuplets[0].numberNotesNormal == 4


def test_export_musicxml_minor_key_signature_parsed():
    """'A minor' must stay minor — the legacy splitter collapsed it to A major."""
    import music21

    xml, _ = _build_musicxml([(0.0, 0.5, 60, 100)], key="A minor")

    score = music21.converter.parse(xml)
    key_sig = list(score.flatten().getElementsByClass(music21.key.Key))[0]
    assert key_sig.tonic.name == "A"
    assert key_sig.mode == "minor"
