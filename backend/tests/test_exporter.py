from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


# --- MusicXML 3.1 Partwise DTD / XSD Validation (Commit 108) ---


def _generate_sample_musicxml() -> str:
    """Build a representative MusicXML document for schema validation."""
    from app.schemas import (
        BeatGrid,
        ChordEvent,
        ChordTimeline,
        SoloNote,
        SoloNotes,
        TimeSignature,
    )
    from app.musicxml_builder import build_musicxml

    beat_grid = BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
        downbeats=[0.0, 2.0],
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
    )
    chord_timeline = ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.85),
        ]
    )
    solo_notes = SoloNotes(
        notes=[
            SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100),
            SoloNote(start_time=0.5, duration=0.25, pitch=62, velocity=80),
            SoloNote(start_time=2.0, duration=1.0, pitch=64, velocity=90),
        ]
    )
    return build_musicxml(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        title="Validation Test",
        artist="CI",
        key_signature="C major",
    )


def test_musicxml_well_formed_xml() -> None:
    """MusicXML output must be well-formed XML (parseable without error)."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)
    assert root.tag == "score-partwise", f"Expected root <score-partwise>, got <{root.tag}>"


def test_musicxml_xsd_schema_validation() -> None:
    """MusicXML output must validate against the Harmoniq MusicXML XSD subset.

    The XSD covers all elements generated by musicxml_builder.py:
    score-partwise, part-list, part, measure, attributes, divisions, key,
    time, note, pitch, beam, tie, harmony, root, kind, frame, technical,
    dynamics, articulations, slur, defaults, scaling, page-layout,
    system-layout, staff-layout.
    """
    from lxml import etree

    xsd_path = FIXTURES_DIR / "musicxml-harmoniq.xsd"
    if not xsd_path.exists():
        pytest.skip("musicxml-harmoniq.xsd not present in fixtures")

    xsd_doc = etree.parse(str(xsd_path))
    xsd_schema = etree.XMLSchema(xsd_doc)

    xml_str = _generate_sample_musicxml()
    xml_doc = etree.fromstring(xml_str.encode("utf-8"))

    is_valid = xsd_schema.validate(xml_doc)
    if not is_valid:
        errors = xsd_schema.error_log
        pytest.fail(
            "MusicXML failed XSD validation:\n"
            + "\n".join(f"  line {e.line}: {e.message}" for e in errors)
        )


def test_musicxml_has_required_root_elements() -> None:
    """MusicXML must contain score-partwise > part-list and at least one part."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    # Must have <part-list> with at least one <score-part>
    part_list = root.find("part-list")
    assert part_list is not None, "Missing <part-list>"
    score_parts = part_list.findall("score-part")
    assert len(score_parts) >= 1, "No <score-part> in <part-list>"

    # Must have at least one <part>
    parts = root.findall("part")
    assert len(parts) >= 1, "No <part> elements"


def test_musicxml_has_divisions_in_first_measure() -> None:
    """First measure must declare <divisions> for unambiguous durations."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    first_part = root.find("part")
    assert first_part is not None
    first_measure = first_part.find("measure")
    assert first_measure is not None

    attributes = first_measure.find("attributes")
    assert attributes is not None, "First measure missing <attributes>"
    divisions = attributes.find("divisions")
    assert divisions is not None, "Missing <divisions> in first measure"
    assert int(divisions.text) > 0, "Divisions must be positive"


def test_musicxml_has_defaults_block() -> None:
    """MusicXML must include <defaults> with scaling and layout info."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    defaults = root.find("defaults")
    assert defaults is not None, "Missing <defaults> block"

    scaling = defaults.find("scaling")
    assert scaling is not None, "Missing <scaling> in <defaults>"
    millimeters = scaling.find("millimeters")
    assert millimeters is not None, "Missing <millimeters>"
    tenths = scaling.find("tenths")
    assert tenths is not None, "Missing <tenths>"

    page_layout = defaults.find("page-layout")
    assert page_layout is not None, "Missing <page-layout>"

    system_layout = defaults.find("system-layout")
    assert system_layout is not None, "Missing <system-layout>"


def test_musicxml_has_harmony_elements() -> None:
    """Chord symbols must be rendered as <harmony> elements."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    harmonies = root.findall(".//harmony")
    assert len(harmonies) >= 1, "No <harmony> elements found"
    for h in harmonies:
        assert h.find("root") is not None or h.find("chord") is not None, (
            "<harmony> must have <root> or <chord>"
        )


def test_musicxml_has_time_signature() -> None:
    """MusicXML must declare the correct time signature."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    first_part = root.find("part")
    first_measure = first_part.find("measure")
    attributes = first_measure.find("attributes")
    time = attributes.find("time")
    assert time is not None, "Missing <time> in <attributes>"
    assert time.find("beats").text == "4"
    assert time.find("beat-type").text == "4"


def test_musicxml_has_key_signature() -> None:
    """MusicXML must declare the correct key signature."""
    from xml.etree.ElementTree import fromstring

    xml_str = _generate_sample_musicxml()
    root = fromstring(xml_str)

    first_part = root.find("part")
    first_measure = first_part.find("measure")
    attributes = first_measure.find("attributes")
    key = attributes.find("key")
    assert key is not None, "Missing <key> in <attributes>"
    fifths = key.find("fifths")
    assert fifths is not None, "Missing <fifths>"
    assert int(fifths.text) == 0, "C major should have 0 sharps/flats"
