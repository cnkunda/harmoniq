"""alphatab_prerender helper tests — PRIORITIES §59."""

from __future__ import annotations

import base64

import pytest
import shutil

from app.alphatab_prerender import enrich_lesson_with_prerender_hints, prerender_cache_key, prerender_enabled, score_sha256_from_gp5_base64
from app.schemas import LessonJSON


def test_score_sha_deterministic():
    b64 = base64.b64encode(b"stub-guitar-pro-test-bytes").decode("ascii")
    h1 = score_sha256_from_gp5_base64(b64)
    h2 = score_sha256_from_gp5_base64(b64)
    assert h1 == h2
    assert len(h1) == 64


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
    raw = _run_node_prerender(b64)
    assert raw.get("ok") is True
    assert int(raw.get("partial_count") or 0) >= 1
