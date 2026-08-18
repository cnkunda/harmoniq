"""alphatab_prerender helper tests — PRIORITIES §59."""

from __future__ import annotations

import base64

import pytest
import shutil

from app.alphatab_prerender import (
    enrich_lesson_with_prerender_hints,
    prerender_cache_key,
    prerender_enabled,
    score_sha256_from_gp5_base64,
    score_sha256_from_musicxml,
)
from app.schemas import LessonJSON


def test_score_sha_deterministic():
    b64 = base64.b64encode(b"stub-guitar-pro-test-bytes").decode("ascii")
    h1 = score_sha256_from_gp5_base64(b64)
    h2 = score_sha256_from_gp5_base64(b64)
    assert h1 == h2
    assert len(h1) == 64


def test_score_sha_musicxml_deterministic():
    """Commit 107: MusicXML hashes its own raw XML (whitespace-insensitive at edges)."""
    xml = "<score-partwise version=\"3.1\"><part-list/></score-partwise>"
    h1 = score_sha256_from_musicxml(xml)
    h2 = score_sha256_from_musicxml("  " + xml + "\n")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != score_sha256_from_musicxml(xml.replace("3.1", "3.0"))


def test_prerender_cache_key_stable():
    k = prerender_cache_key("aa" * 32)
    assert k == prerender_cache_key("aa" * 32)
    assert len(k) == 64


def test_prerender_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HARMONIQ_ENABLE_PRERENDER", raising=False)
    monkeypatch.delenv("HARMONIQ_SKIP_PRERENDER", raising=False)
    assert prerender_enabled() is False


def test_skip_overrides_enable(monkeypatch):
    monkeypatch.setenv("HARMONIQ_ENABLE_PRERENDER", "1")
    monkeypatch.setenv("HARMONIQ_SKIP_PRERENDER", "1")
    assert prerender_enabled() is False


def test_enrich_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("HARMONIQ_ENABLE_PRERENDER", raising=False)
    monkeypatch.delenv("HARMONIQ_SKIP_PRERENDER", raising=False)
    gp5 = base64.b64encode(b"x").decode("ascii")
    lesson = LessonJSON(job_id="job-x")
    out = enrich_lesson_with_prerender_hints(lesson, job_id="job-x", gp5_base64=gp5)
    assert out.alphatab_prerender_hints is None


def test_node_bridge_smoke_if_available(tmp_path):
    """Optional: exercises Node + AlphaTab when deps and `node` exist."""
    import base64

    pytest.importorskip("guitarpro")

    from app.alphatab_prerender import _node_script_path, _run_node_prerender
    from app.pipeline_proof import NoteEvent, build_gp5_from_note_events

    if shutil.which("node") is None:
        return
    script = _node_script_path()
    if not script.is_file():
        return

    gp5_path = tmp_path / "tiny.gp5"
    build_gp5_from_note_events(
        [NoteEvent(start_s=0.0, end_s=0.5, pitch_midi=64, amplitude=1.0)],
        bpm=120,
        output_gp5=gp5_path,
        title="prerender smoke",
    )
    b64 = base64.b64encode(gp5_path.read_bytes()).decode("ascii")
    raw = _run_node_prerender(gp5_base64=b64)
    assert raw.get("ok") is True
    assert int(raw.get("partial_count") or 0) >= 1


def test_node_bridge_musicxml_smoke_if_available():
    """Commit 107: Node + AlphaTab renders MusicXML input (primary prerender path)."""
    from app.alphatab_prerender import _node_script_path, _run_node_prerender

    if shutil.which("node") is None:
        return
    script = _node_script_path()
    if not script.is_file():
        return

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Lead</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>
    </measure>
  </part>
</score-partwise>"""
    raw = _run_node_prerender(musicxml=xml)
    assert raw.get("ok") is True
    assert int(raw.get("master_bar_count") or 0) == 1
    assert int(raw.get("partial_count") or 0) >= 1
